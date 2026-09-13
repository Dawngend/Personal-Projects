"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { MathPrompt } from "@/components/study/math-prompt";
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
          <h1>{data.title}</h1>
          <p>
            Built from {data.moduleIds.length} source module{data.moduleIds.length === 1 ? "" : "s"}
            . Updated {data.updatedAt.slice(0, 10)}.
          </p>
        </header>

        {data.content.sections.map((section, index) => (
          <section className={styles.section} key={`${section.heading}-${index}`}>
            <p className={styles.sectionNumber}>Section {String(index + 1).padStart(2, "0")}</p>
            <h2>{section.heading}</h2>
            <div className={styles.summary}>
              <MathPrompt>{section.summary}</MathPrompt>
            </div>
            {section.keyTerms.length > 0 && (
              <div className={styles.block}>
                <h3>Key terms</h3>
                <dl className={styles.definitionGrid}>
                  {section.keyTerms.map((item) => (
                    <div key={item.term}>
                      <dt>{item.term}</dt>
                      <dd>{item.definition}</dd>
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
                    <strong>{item.name}</strong>
                    <MathPrompt>{item.statement}</MathPrompt>
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
                    <MathPrompt>{example.problem}</MathPrompt>
                    <ol>
                      {example.steps.map((step, stepIndex) => (
                        <li key={`${step}-${stepIndex}`}>
                          <MathPrompt>{step}</MathPrompt>
                        </li>
                      ))}
                    </ol>
                    <div className={styles.answer}>
                      <strong>Answer</strong>
                      <MathPrompt>{example.answer}</MathPrompt>
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
                    <li key={mistake}>{mistake}</li>
                  ))}
                </ul>
              </aside>
            )}
            {section.sourceRefs.length > 0 && (
              <p className={styles.sources}>Sources: {section.sourceRefs.join(" · ")}</p>
            )}
          </section>
        ))}

        {data.content.formulaSheet.length > 0 && (
          <section className={styles.section}>
            <p className={styles.sectionNumber}>Reference</p>
            <h2>Formula sheet</h2>
            <div className={styles.formulaTable}>
              {data.content.formulaSheet.map((formula) => (
                <div className={styles.formulaRow} key={formula.name}>
                  <strong>{formula.name}</strong>
                  <MathPrompt>{formula.expression}</MathPrompt>
                  <span>{formula.whenToUse}</span>
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
                  <strong>{item.question}</strong>
                  <p>{item.answer}</p>
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
