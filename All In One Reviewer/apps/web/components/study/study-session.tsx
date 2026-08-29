"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { GradeResult, MatchedTier, QuizCard, RevealResult } from "@/lib/contracts";
import { MathPrompt } from "./math-prompt";
import styles from "./study-session.module.css";

const typeMeta = {
  multiple_choice: ["01", "Multiple choice"],
  enumeration: ["02", "Enumeration"],
  problem: ["03", "Problem"],
} as const;
const draftKey = (sessionId: string, cardId: number, field: "answer" | "scratch") =>
  `andyhub:study:${sessionId}:${cardId}:${field}`;

function SessionProgress({
  card,
  index,
  total,
  grade,
  reveal,
}: {
  card: QuizCard;
  index: number;
  total: number;
  grade: GradeResult | null;
  reveal: RevealResult | null;
}) {
  const [symbol, label] = typeMeta[card.type];
  // Use grade.complete (server-owned resolved state), not grade.correct (this submission only) --
  // otherwise a stray resubmit on an already-solved card renders it as missed.
  const state = reveal ? "revealed" : grade?.complete ? "complete" : grade ? "missed" : "current";
  return (
    <aside className={styles.gutter} aria-label="Session structure">
      <p className={styles.gutterTitle}>Reasoning trace</p>
      <ol>
        <li className={styles.current}>
          <i aria-hidden="true" />
          <div>
            <strong>
              Question {String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
            </strong>
            <small>Server-owned position</small>
          </div>
        </li>
        <li>
          <i aria-hidden="true" />
          <div>
            <strong>
              {symbol} · {label}
            </strong>
            <small>Current card type</small>
          </div>
        </li>
        <li
          className={
            state === "missed" || state === "revealed"
              ? styles.missed
              : state === "complete"
                ? styles.complete
                : ""
          }
        >
          <i aria-hidden="true" />
          <div>
            <strong>
              {state === "revealed"
                ? "Revealed"
                : state === "missed"
                  ? "Missed · retry open"
                  : state === "complete"
                    ? "Resolved"
                    : "Attempt pending"}
            </strong>
            <small>
              {state === "revealed"
                ? "Solution recorded by session"
                : state === "missed"
                  ? "Your draft stays in place"
                  : "Progress updates only after a server response"}
            </small>
          </div>
        </li>
      </ol>
    </aside>
  );
}

/**
 * Explain a match that was accepted in a different written form. "exact" needs
 * no explanation, so it returns null and nothing is rendered.
 */
function equivalentFormNote(tier: MatchedTier | null | undefined): string | null {
  switch (tier) {
    case "numeric":
      return "Your answer was read as a number, so a fraction, percent, or rounded decimal counts.";
    case "structured":
      return "Your answer was compared entry by entry, so spacing and bracket style do not matter.";
    case "symbolic":
      return "Your answer was checked algebraically, so an equivalent expression counts.";
    default:
      return null;
  }
}

function Feedback({ grade, reveal }: { grade: GradeResult | null; reveal: RevealResult | null }) {
  const expected = reveal?.expectedAnswer ?? grade?.expectedAnswer;
  const steps = reveal?.solutionSteps ?? grade?.solutionSteps;
  const equivalentForm = grade?.correct ? equivalentFormNote(grade.matchedTier) : null;
  if (!grade && !reveal) return null;
  return (
    <section
      className={`${styles.feedback} ${grade?.complete ? styles.feedbackCorrect : ""}`}
      aria-live="polite"
    >
      <p>
        {reveal
          ? "Worked solution revealed. This card is marked missed for this session."
          : grade?.feedback}
      </p>
      {equivalentForm ? (
        <div className={styles.equivalentForm}>
          <strong>Equivalent form</strong>
          <p>{equivalentForm}</p>
        </div>
      ) : null}
      {grade?.caughtItems?.length ? (
        <div>
          <strong>Caught</strong>
          <ul className={styles.tokens}>
            {grade.caughtItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {grade?.missedItems?.length ? (
        <div>
          <strong>Still missing</strong>
          <ul className={styles.tokens}>
            {grade.missedItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {expected ? (
        <p className={styles.referenceAnswer}>
          Reference final answer: <code>{expected}</code>
        </p>
      ) : null}
      {steps?.length ? (
        <div className={styles.stepRail}>
          <p className="eyebrow">{reveal ? "Worked solution" : "Verified solution trace"}</p>
          <ol>
            {steps.map((step, index) => (
              <li key={`${index}-${step}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <MathPrompt>{step}</MathPrompt>
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </section>
  );
}

function MultipleChoiceQuestion({
  card,
  disabledChoices,
  onSelect,
  pending,
}: {
  card: Extract<QuizCard, { type: "multiple_choice" }>;
  disabledChoices: string[];
  onSelect: (value: string) => void;
  pending: boolean;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey ||
        ["INPUT", "TEXTAREA"].includes((event.target as HTMLElement)?.tagName)
      )
        return;
      const index = Number(event.key) - 1;
      if (
        index >= 0 &&
        index < card.options.length &&
        !disabledChoices.includes(card.options[index])
      ) {
        event.preventDefault();
        onSelect(card.options[index]);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [card.options, disabledChoices, onSelect]);
  return (
    <div className={styles.choices} role="radiogroup" aria-label="Answer choices">
      {card.options.map((option, index) => {
        const disabled = pending || disabledChoices.includes(option);
        return (
          <button
            type="button"
            role="radio"
            aria-checked={false}
            aria-label={`Option ${index + 1}: ${option}${disabled ? ", incorrect choice disabled" : ""}`}
            className={`${styles.choice} ${disabled ? styles.choiceMissed : ""}`}
            disabled={disabled}
            onClick={() => onSelect(option)}
            key={option}
          >
            <span>{index + 1}</span>
            <MathPrompt>{option}</MathPrompt>
            {disabled && <b>Missed</b>}
          </button>
        );
      })}
      <p className={styles.shortcut}>
        Use 1–{card.options.length} to choose. Incorrect choices disable; choose another to retry.
      </p>
    </div>
  );
}

function EnumerationQuestion({
  card,
  value,
  onChange,
  onCheck,
  pending,
  resolved,
}: {
  card: Extract<QuizCard, { type: "enumeration" }>;
  value: string;
  onChange: (value: string) => void;
  onCheck: () => void;
  pending: boolean;
  resolved: boolean;
}) {
  return (
    <div className={styles.answerArea}>
      <p className={styles.expected}>
        Recall <strong>{card.expectedCount}</strong> items. Separate them with commas or new lines.
      </p>
      <label className="eyebrow" htmlFor="enumeration-answer">
        Your response
      </label>
      <textarea
        id="enumeration-answer"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Write everything you can recall…"
        rows={8}
      />
      <button type="button" onClick={onCheck} disabled={pending || resolved || !value.trim()}>
        Check answer
      </button>
    </div>
  );
}

function ProblemQuestion({
  card,
  value,
  scratch,
  onValueChange,
  onScratchChange,
  onCheck,
  onReveal,
  pending,
  resolved,
}: {
  card: Extract<QuizCard, { type: "problem" }>;
  value: string;
  scratch: string;
  onValueChange: (value: string) => void;
  onScratchChange: (value: string) => void;
  onCheck: () => void;
  onReveal: () => void;
  pending: boolean;
  resolved: boolean;
}) {
  return (
    <div className={styles.answerArea}>
      <p className={styles.expected}>
        {card.answerFormatHint ??
          "Enter a final answer. Structured work can be checked against the worked solution."}
      </p>
      <label className="eyebrow" htmlFor="problem-answer">
        Final answer
      </label>
      <input
        id="problem-answer"
        value={value}
        onChange={(event) => onValueChange(event.target.value)}
        placeholder="e.g. 24 or x = 3"
      />
      <div className={styles.scratch}>
        <label className="eyebrow" htmlFor="problem-scratch">
          Scratchpad <span>local only</span>
        </label>
        <textarea
          id="problem-scratch"
          value={scratch}
          onChange={(event) => onScratchChange(event.target.value)}
          placeholder="Work through the calculation here. This is not sent to Andy."
          rows={8}
        />
      </div>
      <div className={styles.problemActions}>
        <button type="button" onClick={onCheck} disabled={pending || resolved || !value.trim()}>
          Check answer
        </button>
        <button
          type="button"
          className={styles.reveal}
          onClick={onReveal}
          disabled={pending || resolved}
        >
          Reveal worked solution
        </button>
      </div>
    </div>
  );
}

function SessionSummary({ sessionId, deckId }: { sessionId: string; deckId: number }) {
  const router = useRouter();
  const summary = useQuery({
    queryKey: ["session-summary", sessionId],
    queryFn: () => api.getSessionSummary(sessionId),
  });
  const restart = useMutation({
    mutationFn: (mode: "all" | "missed") => api.startSession(deckId, mode),
    onSuccess: (session) => router.push(`/study/${session.id}`),
  });
  if (summary.isLoading)
    return <main className={styles.summary}>Preparing your session summary…</main>;
  if (summary.isError || !summary.data)
    return (
      <main className={styles.summary}>
        <p className="eyebrow">Session complete</p>
        <h1>Your session finished, but the summary is unavailable.</h1>
        <button type="button" onClick={() => void summary.refetch()}>
          Retry summary
        </button>
      </main>
    );
  const data = summary.data;
  return (
    <main className={styles.summary}>
      <p className="eyebrow">Session complete</p>
      <h1>Trace recorded.</h1>
      <p>
        {data.correct} independently correct out of {data.totalQuestions} cards; {data.attempted}{" "}
        cards received an answer or reveal event.
      </p>
      <dl>
        <div>
          <dt>Missed</dt>
          <dd>{data.missedCardIds.length}</dd>
        </div>
        <div>
          <dt>Revealed</dt>
          <dd>{data.revealedCardIds.length}</dd>
        </div>
        <div>
          <dt>Complete</dt>
          <dd>{data.complete ? "Yes" : "No"}</dd>
        </div>
      </dl>
      {data.missedCardIds.length > 0 && (
        <p className={styles.idList}>Missed card IDs: {data.missedCardIds.join(", ")}</p>
      )}
      {data.revealedCardIds.length > 0 && (
        <p className={styles.idList}>Revealed card IDs: {data.revealedCardIds.join(", ")}</p>
      )}
      <div className={styles.summaryActions}>
        <button type="button" onClick={() => restart.mutate("all")} disabled={restart.isPending}>
          Reflash entire deck
        </button>
        <button
          type="button"
          className={styles.reveal}
          onClick={() => restart.mutate("missed")}
          disabled={restart.isPending || !data.missedCardIds.length}
        >
          Practice missed
        </button>
        <Link href={`/decks/${deckId}`}>Return to deck</Link>
      </div>
      {restart.isError && (
        <p role="alert" className={styles.summaryError}>
          {restart.error.message}
        </p>
      )}
    </main>
  );
}

export function StudySession({ sessionId }: { sessionId: string }) {
  const queryClient = useQueryClient();
  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId),
    retry: false,
  });
  const [answer, setAnswer] = useState("");
  const [scratch, setScratch] = useState("");
  const [grade, setGrade] = useState<GradeResult | null>(null);
  const [reveal, setReveal] = useState<RevealResult | null>(null);
  const [missedChoices, setMissedChoices] = useState<string[]>([]);
  const card = session.data?.card;
  useEffect(() => {
    if (!card) return;
    setAnswer(sessionStorage.getItem(draftKey(sessionId, card.id, "answer")) ?? "");
    setScratch(sessionStorage.getItem(draftKey(sessionId, card.id, "scratch")) ?? "");
    setGrade(null);
    setReveal(null);
    setMissedChoices([]);
  }, [sessionId, card?.id]);
  const saveAnswer = (value: string) => {
    setAnswer(value);
    if (card) sessionStorage.setItem(draftKey(sessionId, card.id, "answer"), value);
  };
  const saveScratch = (value: string) => {
    setScratch(value);
    if (card) sessionStorage.setItem(draftKey(sessionId, card.id, "scratch"), value);
  };
  const submit = useMutation({
    mutationFn: (value: string) => {
      if (!card) throw new Error("No current card.");
      return api.submitAnswer(sessionId, card.id, { type: card.type, value });
    },
    onSuccess: setGrade,
  });
  const revealSolution = useMutation({
    mutationFn: () => {
      if (!card || card.type !== "problem") throw new Error("No problem card to reveal.");
      return api.revealSolution(sessionId, card.id);
    },
    onSuccess: setReveal,
  });
  const advance = useMutation({
    mutationFn: () => api.advanceSession(sessionId),
    onSuccess: (next) => queryClient.setQueryData(["session", sessionId], next),
  });
  if (session.isLoading) return <main className={styles.state}>Restoring your session…</main>;
  if (session.isError || !session.data)
    return (
      <main className={styles.state}>
        <p className="eyebrow">Session unavailable</p>
        <h1>This study session could not resume.</h1>
        <p>Your typed draft remains in this browser until the session can reconnect.</p>
        <button type="button" onClick={() => void session.refetch()}>
          Retry session
        </button>
        <Link href="/">Return to workspace</Link>
      </main>
    );
  if (session.data.complete || !card)
    return <SessionSummary sessionId={sessionId} deckId={session.data.deck.id} />;
  const resolved = Boolean(grade?.complete || reveal);
  const choose = (value: string) =>
    submit.mutate(value, {
      onSuccess: (result) => {
        if (!result.correct) setMissedChoices((current) => [...new Set([...current, value])]);
      },
    });
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href={`/decks/${session.data.deck.id}`} className={styles.wordmark}>
          Andy<span>Hub</span>
        </Link>
        <span>{session.data.deck.name}</span>
      </header>
      <div className={styles.studyGrid}>
        <SessionProgress
          card={card}
          index={session.data.currentIndex}
          total={session.data.totalQuestions}
          grade={grade}
          reveal={reveal}
        />
        <section className={styles.question}>
          <p className="eyebrow">
            {typeMeta[card.type][0]} · {typeMeta[card.type][1]}
          </p>
          <MathPrompt>{card.question}</MathPrompt>
          {card.type === "multiple_choice" && (
            <MultipleChoiceQuestion
              card={card}
              disabledChoices={missedChoices}
              pending={submit.isPending}
              onSelect={choose}
            />
          )}
          {card.type === "enumeration" && (
            <EnumerationQuestion
              card={card}
              value={answer}
              onChange={saveAnswer}
              onCheck={() => submit.mutate(answer)}
              pending={submit.isPending}
              resolved={resolved}
            />
          )}
          {card.type === "problem" && (
            <ProblemQuestion
              card={card}
              value={answer}
              scratch={scratch}
              onValueChange={saveAnswer}
              onScratchChange={saveScratch}
              onCheck={() => submit.mutate(answer)}
              onReveal={() => revealSolution.mutate()}
              pending={submit.isPending || revealSolution.isPending}
              resolved={resolved}
            />
          )}
          {submit.isError && (
            <p className={styles.error} role="alert">
              {submit.error.message}
            </p>
          )}
          {revealSolution.isError && (
            <p className={styles.error} role="alert">
              {revealSolution.error.message}
            </p>
          )}
          <Feedback grade={grade} reveal={reveal} />
          {resolved && (
            <button
              type="button"
              className={styles.advance}
              onClick={() => advance.mutate()}
              disabled={advance.isPending}
            >
              {advance.isPending
                ? "Advancing…"
                : session.data.currentIndex + 1 === session.data.totalQuestions
                  ? "View session summary →"
                  : "Next question →"}
            </button>
          )}
          {advance.isError && (
            <p className={styles.error} role="alert">
              {advance.error.message}
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
