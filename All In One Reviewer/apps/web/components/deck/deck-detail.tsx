"use client";

import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { QuizCard } from "@/lib/contracts";
import { MathPrompt } from "@/components/study/math-prompt";
import styles from "./deck-detail.module.css";

const labels = { multiple_choice: "Multiple choice", enumeration: "Enumeration", problem: "Problem" };

function CardPreview({ card, position }: { card: QuizCard; position: number }) {
  return <li className={styles.preview}><span className={styles.cardMeta}>#{String(position + 1).padStart(2, "0")} · card {card.id} · {labels[card.type]}</span><MathPrompt>{card.question}</MathPrompt>{card.type === "multiple_choice" && <><p className={styles.optionCount}>{card.options.length} choices — no option is marked as correct.</p><ol className={styles.options}>{card.options.map((option, index) => <li key={option}><span>{index + 1}</span><MathPrompt>{option}</MathPrompt></li>)}</ol></>}{card.type === "enumeration" && <p className={styles.optionCount}>Recall {card.expectedCount} items.</p>}{card.type === "problem" && <p className={styles.optionCount}>{card.answerFormatHint ?? "Final answer required"}</p>}</li>;
}

export function DeckDetail({ deckId }: { deckId: number }) {
  const router = useRouter();
  const deck = useQuery({ queryKey: ["deck", deckId], queryFn: () => api.getDeck(deckId), retry: false });
  const start = useMutation({ mutationFn: (mode: "all" | "missed") => api.startSession(deckId, mode), onSuccess: (session) => router.push(`/study/${session.id}`) });
  if (deck.isLoading) return <main className={styles.state}>Reading your deck…</main>;
  if (deck.isError || !deck.data) return <main className={styles.state}><p className="eyebrow">Deck unavailable</p><h1>Andy could not read this deck.</h1><p>The deck may be unavailable, or the local API may be offline. No answers were requested.</p><button type="button" onClick={() => void deck.refetch()}>Retry loading deck</button><Link href="/">Return to library</Link></main>;
  const data = deck.data;
  return <main className={styles.page}>
    <header className={styles.header}><Link href="/" className={styles.wordmark}>Andy<span>Hub</span></Link><Link href="/" className={styles.back}>← Study workspace</Link></header>
    <section className={styles.hero}><p className="eyebrow">{data.subject} · deck {String(data.id).padStart(3, "0")}</p><h1>{data.name}</h1><p>{data.cardCount} safe card previews from {data.modules.length} source module{data.modules.length === 1 ? "" : "s"}.</p></section>
    <section className={styles.actions} aria-label="Start study"><div><p className="eyebrow">Ready to study</p><h2>Choose a session path</h2><p>Session order, attempts, and progress are stored by the API, so reopening this session resumes the same card.</p></div><div className={styles.actionButtons}><button type="button" onClick={() => start.mutate("all")} disabled={start.isPending}>Start all →</button><button type="button" className={styles.secondary} onClick={() => start.mutate("missed")} disabled={start.isPending}>Practice missed</button></div>{start.isError && <p className={styles.actionError} role="alert">{start.error.message}</p>}</section>
    <div className={styles.grid}><section><p className="eyebrow">Source modules</p><ul className={styles.modules}>{data.modules.map((module) => <li key={module}>{module}</li>)}</ul><p className="eyebrow">Question composition</p><dl className={styles.composition}>{Object.entries(labels).map(([type, label]) => <div key={type}><dt>{label}</dt><dd>{data.questionTypes[type] ?? 0}</dd></div>)}</dl><aside className={styles.provenance}><p className="eyebrow">Generation provenance</p><p>This deck is persisted from the listed source modules. Card previews use the API’s safe card payloads; answer keys and worked steps are not present here.</p><p className={styles.mono}>Recorded misses: {data.totalMisses}</p></aside></section>
      <section><div className={styles.previewHead}><div><p className="eyebrow">Card previews</p><h2>Questions, not answers</h2></div><span>{data.cards?.length ?? 0} cards</span></div>{data.cards?.length ? <ol className={styles.previews}>{data.cards.map((card, index) => <CardPreview card={card} position={index} key={card.id} />)}</ol> : <p className={styles.noCards}>This deck has no safe preview cards available. Try reloading; no retry can regenerate it without an explicit new generation request.</p>}</section></div>
  </main>;
}
