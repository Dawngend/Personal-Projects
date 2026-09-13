import katex from "katex";
import styles from "./note-detail.module.css";

export type MathTextPart =
  { kind: "text"; source: string } | { kind: "math"; source: string; display: boolean };

const mathPattern =
  /\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\begin\{(bmatrix|pmatrix|vmatrix|array)\}[\s\S]+?\\end\{\1\}|\\\([\s\S]+?\\\)|(?<![\\$])\$(?!\$)[^$\r\n]+?(?<![\\$])\$(?!\$)|(?:[A-Za-z]|\([^()\r\n]{1,80}\))(?:[_^](?:\{[^{}\r\n]+\}|[A-Za-z0-9]))+/g;

function asMathPart(token: string): MathTextPart {
  if (token.startsWith("$$") && token.endsWith("$$")) {
    return { kind: "math", source: token.slice(2, -2), display: true };
  }
  if (token.startsWith("\\[") && token.endsWith("\\]")) {
    return { kind: "math", source: token.slice(2, -2), display: true };
  }
  if (token.startsWith("\\(") && token.endsWith("\\)")) {
    return { kind: "math", source: token.slice(2, -2), display: false };
  }
  if (token.startsWith("$") && token.endsWith("$")) {
    return { kind: "math", source: token.slice(1, -1), display: false };
  }
  return {
    kind: "math",
    source: token,
    display: token.startsWith("\\begin{"),
  };
}

export function splitMathText(text: string): MathTextPart[] {
  const parts: MathTextPart[] = [];
  let cursor = 0;

  for (const match of text.matchAll(mathPattern)) {
    const index = match.index;
    if (index > cursor) parts.push({ kind: "text", source: text.slice(cursor, index) });
    parts.push(asMathPart(match[0]));
    cursor = index + match[0].length;
  }

  if (cursor < text.length) parts.push({ kind: "text", source: text.slice(cursor) });
  if (parts.length === 0) parts.push({ kind: "text", source: text });
  return parts;
}

/** Model text stays escaped; only markup returned by KaTeX is injected. */
export function MathText({ children, mathOnly = false }: { children: string; mathOnly?: boolean }) {
  const parts: MathTextPart[] = mathOnly
    ? [{ kind: "math", source: children, display: false }]
    : splitMathText(children);

  return (
    <span className={styles.mathText}>
      {parts.map((part, index) => {
        if (part.kind === "text") return <span key={index}>{part.source}</span>;

        const className = part.display ? styles.mathDisplay : styles.mathInline;
        try {
          const html = katex.renderToString(part.source, {
            throwOnError: false,
            displayMode: part.display,
            strict: "ignore",
          });
          return (
            <span key={index} className={className} dangerouslySetInnerHTML={{ __html: html }} />
          );
        } catch {
          return (
            <span key={index} className={className}>
              {part.source}
            </span>
          );
        }
      })}
    </span>
  );
}
