"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import styles from "./notes-library.module.css";

export function NotesLibrary() {
  const queryClient = useQueryClient();
  const notes = useQuery({ queryKey: ["notes"], queryFn: api.listNotes });
  const remove = useMutation({
    mutationFn: api.deleteNote,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notes"] }),
  });

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.wordmark} href="/">
          Andy<span>Hub</span>
        </Link>
        <nav aria-label="Notes navigation">
          <Link href="/">Study workspace</Link>
          <Link className={styles.primary} href="/notes/new">
            Generate notes ↗
          </Link>
        </nav>
      </header>
      <section className={styles.hero}>
        <p className="eyebrow">Written reviewers</p>
        <h1>Generated notes.</h1>
        <p>Structured study material built from your modules, ready to read on screen or print.</p>
      </section>
      <section className={styles.library} aria-labelledby="notes-title">
        <div className={styles.libraryHead}>
          <div>
            <p className="eyebrow">Library</p>
            <h2 id="notes-title">Saved written reviewers</h2>
          </div>
          <span>{notes.data?.length ?? 0} notes</span>
        </div>
        {notes.isLoading && <p className={styles.state}>Reading the notes library…</p>}
        {notes.isError && <p className={styles.error}>The API could not load generated notes.</p>}
        {!notes.isLoading && !notes.isError && notes.data?.length === 0 && (
          <div className={styles.empty}>
            <span aria-hidden="true">≡</span>
            <h3>No generated notes yet</h3>
            <p>Choose existing modules and create a printable reviewer at the depth you need.</p>
            <Link href="/notes/new">Generate the first notes</Link>
          </div>
        )}
        <div className={styles.grid}>
          {notes.data?.map((note) => (
            <article key={note.id}>
              <p className="eyebrow">{note.subject}</p>
              <h3>
                <Link href={`/notes/${note.id}`}>{note.title}</Link>
              </h3>
              <p>
                {note.moduleIds.length} source module{note.moduleIds.length === 1 ? "" : "s"} ·{" "}
                {note.createdAt.slice(0, 10)}
              </p>
              <div>
                <Link href={`/notes/${note.id}`}>Open notes →</Link>
                <button
                  type="button"
                  onClick={() => remove.mutate(note.id)}
                  disabled={remove.isPending}
                  aria-label={`Delete ${note.title}`}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
        {remove.isError && <p className={styles.error}>{remove.error.message}</p>}
      </section>
    </main>
  );
}
