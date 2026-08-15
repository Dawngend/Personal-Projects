"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import styles from "./study-workspace.module.css";

export function StudyWorkspace() {
  const decks = useQuery({ queryKey: ["decks"], queryFn: api.listDecks });
  const grouped = (decks.data ?? []).reduce<Record<string, typeof decks.data>>((groups, deck) => {
    (groups[deck.subject] ??= []).push(deck);
    return groups;
  }, {});

  return (
    <main className={styles.workspace}>
      <header className={styles.topline}>
        <Link className={styles.wordmark} href="/" aria-label="AndyHub study workspace">Andy<span>Hub</span></Link>
        <Link className={styles.createLink} href="/decks/new">Create deck <span aria-hidden="true">↗</span></Link>
      </header>
      <section className={styles.intro} aria-labelledby="workspace-title">
        <p className={styles.kicker}>Study workspace · local course memory</p>
        <h1 id="workspace-title">Make the next proof of understanding.</h1>
        <p>Choose a reviewer, or plant a new set of source materials for Andy to turn into active recall.</p>
      </section>
      <section className={styles.continue} aria-labelledby="continue-title">
        <div><p className={styles.kicker}>Current thread</p><h2 id="continue-title">No session is in progress</h2><p>Your deck library stays here; focused quiz sessions arrive in the next study phase.</p></div>
        <Link href="/decks/new" className={styles.primary}>Create a deck <span aria-hidden="true">→</span></Link>
      </section>
      <section className={styles.library} aria-labelledby="library-title">
        <div className={styles.libraryHead}><div><p className={styles.kicker}>Library</p><h2 id="library-title">Study material, grouped by subject</h2></div><span className={styles.mono}>{decks.data?.length ?? 0} decks</span></div>
        {decks.isLoading && <p className={styles.state}>Reading the deck library…</p>}
        {decks.isError && <p className={styles.error}>The API could not load your decks. Check that the FastAPI service is reachable.</p>}
        {!decks.isLoading && !decks.isError && decks.data?.length === 0 && (
          <div className={styles.empty}><span aria-hidden="true">✣</span><h3>No decks yet</h3><p>Upload PDFs or slide decks, choose a question style, and generate your first reviewer.</p><Link href="/decks/new">Start with materials</Link></div>
        )}
        {Object.entries(grouped).map(([subject, subjectDecks]) => <div className={styles.subject} key={subject}><h3>{subject}</h3><div className={styles.deckGrid}>{subjectDecks?.map((deck) => <article className={styles.deck} key={deck.id}><p className={styles.mono}>DECK {String(deck.id).padStart(3, "0")}</p><h4><Link href={`/decks/${deck.id}`}>{deck.name}</Link></h4><p>{deck.cardCount} cards · {deck.totalMisses} recorded misses</p><div>{Object.entries(deck.questionTypes).filter(([, count]) => count).map(([type, count]) => <span key={type}>{type.replace("_", " ")} {count}</span>)}</div></article>)}</div></div>)}
      </section>
    </main>
  );
}
