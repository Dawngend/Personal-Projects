import katex from "katex";

/** Renders only KaTeX-generated markup; model text itself is never injected as HTML. */
export function MathPrompt({ children }: { children: string }) {
  const pieces = children.split(/(\$\$[\s\S]+?\$\$|\\\([\s\S]+?\\\))/g);
  return (
    <div className="math-prompt">
      {pieces.map((piece, index) => {
        const display = piece.startsWith("$$") && piece.endsWith("$$");
        const inline = piece.startsWith("\\(") && piece.endsWith("\\)");
        if (!display && !inline) return <span key={index}>{piece}</span>;
        return (
          <span
            key={index}
            className={display ? "math-display" : "math-inline"}
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(piece.slice(2, -2), {
                displayMode: display,
                throwOnError: false,
                strict: "ignore",
              }),
            }}
          />
        );
      })}
    </div>
  );
}
