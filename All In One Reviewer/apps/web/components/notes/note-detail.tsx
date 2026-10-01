"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { MathText } from "./math-text";
import styles from "./note-detail.module.css";

export function NoteDetailView({ noteId }: { noteId: number }) {
  const router = useRouter();
  const note = useQuery({
    queryKey: ["note", noteId],
    queryFn: () => api.getNote(noteId),
    retry: false,
  });
  const remove = useMutation({
    mutationFn: () => api.deleteNote(noteId),
    onSuccess: () => router.push("/notes"),
  });

  if (note.isLoading) return <main className={styles.state}>Reading generated notes…</main>;
  if (note.isError || !note.data)
    return (
      <main className={styles.state}>
        <p className="eyebrow">Notes unavailable</p>
        <h1>Andy could not read these notes.</h1>
        <button type="button" onClick={() => void note.refetch()}>
          Retry loading
        </button>
        <Link href="/notes">Return to notes</Link>
      </main>
    );

  const data = note.data;
  return (
    <main className={styles.page}>
      <header className={`${styles.header} ${styles.screenOnly}`}>
        <Link href="/" className={styles.wordmark}>
          Andy<span>Hub</span>
        </Link>
        <nav aria-label="Note actions">
          <Link href="/notes">← Notes library</Link>
          <button type="button" onClick={() => window.print()}>
            Print
          </button>
          <button
            type="button"
            className={styles.delete}
            onClick={() => remove.mutate()}
            disabled={remove.isPending}
          >
            Delete
          </button>
        </nav>
      </header>
      <article className={styles.document}>
        <header className={styles.titleBlock}>
          <p className={styles.subject}>{data.subject} · generated notes</p>
          <h1>
            <MathText>{data.title}</MathText>
          </h1>
          <p>
            Built from {data.moduleIds.length} source module{data.moduleIds.length === 1 ? "" : "s"}
            . Updated {data.updatedAt.slice(0, 10)}.
          </p>
        </header>

        {data.content.sections.map((section, index) => (
          <section className={styles.section} key={`${section.heading}-${index}`}>
            <p className={styles.sectionNumber}>Section {String(index + 1).padStart(2, "0")}</p>
            <h2>
              <MathText>{section.heading}</MathText>
            </h2>
            <div className={styles.summary}>
              <MathText>{section.summary}</MathText>
            </div>
            {section.memoryAids.length > 0 && (
              <div className={styles.memoryAids}>
                {section.memoryAids.map((aid, aidIndex) => (
                  <aside className={styles.memoryAid} key={`${aid.label}-${aidIndex}`}>
                    <p className={styles.memoryLabel}>Memory aid · {aid.label}</p>
                    <div className={styles.memoryText}>
                      <MathText>{aid.text}</MathText>
                    </div>
                  </aside>
                ))}
              </div>
            )}
            {section.comparisons.map((comparison, comparisonIndex) => (
              <div className={styles.block} key={`${comparison.title}-${comparisonIndex}`}>
                <h3>{comparison.title}</h3>
                <div className={styles.tableScroll}>
                  <table className={styles.comparisonTable}>
                    <thead>
                      <tr>
                        {comparison.columns.map((column, columnIndex) => (
                          <th scope="col" key={`${column}-${columnIndex}`}>
                            <MathText>{column}</MathText>
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.rows.map((row, rowIndex) => (
                        <tr key={`${row[0]}-${rowIndex}`}>
                          {row.map((cell, cellIndex) =>
                            cellIndex === 0 ? (
                              <th scope="row" key={cellIndex}>
                                <MathText>{cell}</MathText>
                              </th>
                            ) : (
                              <td key={cellIndex}>
                                <MathText>{cell}</MathText>
                              </td>
                            ),
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
            {section.keyTerms.length > 0 && (
              <div className={styles.block}>
                <h3>Key terms</h3>
                <dl className={styles.definitionGrid}>
                  {section.keyTerms.map((item) => (
                    <div key={item.term}>
                      <dt>
                        <MathText>{item.term}</MathText>
                      </dt>
                      <dd>
                        <MathText>{item.definition}</MathText>
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            )}
            {section.properties.length > 0 && (
              <div className={styles.theorem}>
                <h3>Properties and principles</h3>
                {section.properties.map((item) => (
                  <div key={item.name}>
                    <strong>
                      <MathText>{item.name}</MathText>
                    </strong>
                    <MathText>{item.statement}</MathText>
                  </div>
                ))}
              </div>
            )}
            {section.workedExamples.length > 0 && (
              <div className={styles.block}>
                <h3>Worked examples</h3>
                {section.workedExamples.map((example, exampleIndex) => (
                  <article
                    className={styles.workedExample}
                    key={`${example.problem}-${exampleIndex}`}
                  >
                    <p className={styles.exampleLabel}>Example {exampleIndex + 1}</p>
                    <MathText>{example.problem}</MathText>
                    <ol>
                      {example.steps.map((step, stepIndex) => (
                        <li key={`${step}-${stepIndex}`}>
                          <MathText>{step}</MathText>
                        </li>
                      ))}
                    </ol>
                    <div className={styles.answer}>
                      <strong>Answer</strong>
                      <MathText>{example.answer}</MathText>
                    </div>
                  </article>
                ))}
              </div>
            )}
            {section.commonMistakes.length > 0 && (
              <aside className={styles.mistakes}>
                <h3>Common mistakes</h3>
                <ul>
                  {section.commonMistakes.map((mistake) => (
                    <li key={mistake}>
                      <MathText>{mistake}</MathText>
                    </li>
                  ))}
                </ul>
              </aside>
            )}
            {section.sourceRefs.length > 0 && (
              <p className={styles.sources}>Sources: {section.sourceRefs.join(" · ")}</p>
            )}
          </section>
        ))}

        {data.content.cramSheet.length > 0 && (
          <section className={`${styles.section} ${styles.cramSheet}`}>
            <p className={styles.sectionNumber}>Last look</p>
            <h2>Cram sheet</h2>
            <dl className={styles.definitionGrid}>
              {data.content.cramSheet.map((item, itemIndex) => (
                <div key={`${item.topic}-${itemIndex}`}>
                  <dt>
                    <MathText>{item.topic}</MathText>
                  </dt>
                  <dd>
                    <MathText>{item.remember}</MathText>
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {data.content.formulaSheet.length > 0 && (
          <section className={styles.section}>
            <p className={styles.sectionNumber}>Reference</p>
            <h2>Formula sheet</h2>
            <div className={styles.formulaTable}>
              {data.content.formulaSheet.map((formula) => (
                <div className={styles.formulaRow} key={formula.name}>
                  <strong>
                    <MathText>{formula.name}</MathText>
                  </strong>
                  <MathText mathOnly>{formula.expression}</MathText>
                  <span>
                    <MathText>{formula.whenToUse}</MathText>
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {data.content.selfCheck.length > 0 && (
          <section className={`${styles.section} ${styles.selfCheck}`}>
            <p className={styles.sectionNumber}>Review</p>
            <h2>Self-check</h2>
            <ol>
              {data.content.selfCheck.map((item) => (
                <li key={item.question}>
                  <strong>
                    <MathText>{item.question}</MathText>
                  </strong>
                  <p>
                    <MathText>{item.answer}</MathText>
                  </p>
                </li>
              ))}
            </ol>
          </section>
        )}
      </article>
      {remove.isError && (
        <p className={`${styles.error} ${styles.screenOnly}`}>{remove.error.message}</p>
      )}
    </main>
  );
}
