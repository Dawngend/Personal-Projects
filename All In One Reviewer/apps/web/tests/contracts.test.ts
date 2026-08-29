import { describe, expect, it } from "vitest";
import {
  DeckDetailSchema,
  GenerationJobSchema,
  GradeResultSchema,
  QuizCardSchema,
  QuizSessionSchema,
  RevealResultSchema,
  SessionSummarySchema,
} from "../lib/contracts";

describe("Phase 2 API client contract", () => {
  it("accepts the safe discriminated quiz-card payloads and rejects answer keys", () => {
    expect(
      QuizCardSchema.parse({ id: 1, type: "multiple_choice", question: "Q", options: ["A", "B"] })
        .type,
    ).toBe("multiple_choice");
    expect(
      QuizCardSchema.parse({ id: 2, type: "enumeration", question: "Q", expectedCount: 3 }).type,
    ).toBe("enumeration");
    expect(
      QuizCardSchema.safeParse({ id: 3, type: "problem", question: "Q", correctAnswer: "24" })
        .success,
    ).toBe(false);
  });

  it("matches the persisted worker status contract used by SSE", () => {
    expect(
      GenerationJobSchema.parse({
        id: "gen_abc",
        status: "running",
        stage: "generating",
        progress: 62,
        message: "Generating questions from module chunk 3 of 5",
        cardsReceived: 12,
        cardsValid: 10,
        deckId: null,
        error: null,
      }).progress,
    ).toBe(62);
  });

  it("validates deck detail and session payloads without accepting answer keys ahead of grading", () => {
    const card = { id: 7, type: "enumeration", question: "List axioms", expectedCount: 3 };
    expect(
      DeckDetailSchema.parse({
        id: 2,
        name: "Algebra",
        subject: "Math",
        modules: ["week-1.pdf"],
        cardCount: 1,
        questionTypes: { enumeration: 1 },
        totalMisses: 0,
        cards: [card],
      }).cards?.[0],
    ).toEqual(card);
    expect(
      QuizSessionSchema.parse({
        id: "quiz_abc",
        deck: { id: 2, name: "Algebra" },
        totalQuestions: 1,
        currentIndex: 0,
        card,
        complete: false,
      }).card?.type,
    ).toBe("enumeration");
    expect(
      QuizSessionSchema.safeParse({
        id: "quiz_abc",
        deck: { id: 2, name: "Algebra" },
        totalQuestions: 1,
        currentIndex: 0,
        card: { ...card, expectedItems: ["closure"] },
        complete: false,
      }).success,
    ).toBe(false);
  });

  it("only permits answer material in post-grade and reveal contracts", () => {
    expect(
      GradeResultSchema.parse({
        correct: false,
        complete: false,
        feedback: "Try again",
        caughtItems: ["closure"],
        missedItems: ["identity"],
        expectedAnswer: null,
        solutionSteps: null,
      }).feedback,
    ).toBe("Try again");
    expect(
      RevealResultSchema.parse({ expectedAnswer: "24", solutionSteps: ["Expand the determinant."] })
        .solutionSteps,
    ).toHaveLength(1);
  });

  it("carries the matched comparison tier without breaking older payloads", () => {
    const base = { correct: true, complete: true, feedback: "Correct." };
    // A verbatim match and an accepted equivalent form must be distinguishable.
    expect(GradeResultSchema.parse({ ...base, matchedTier: "exact" }).matchedTier).toBe("exact");
    expect(GradeResultSchema.parse({ ...base, matchedTier: "numeric" }).matchedTier).toBe("numeric");
    expect(GradeResultSchema.parse({ ...base, matchedTier: "structured" }).matchedTier).toBe(
      "structured",
    );
    expect(GradeResultSchema.parse({ ...base, matchedTier: "symbolic" }).matchedTier).toBe(
      "symbolic",
    );
    // Absent and null both mean "no tier applies", so pre-existing responses parse.
    expect(GradeResultSchema.parse(base).matchedTier).toBeUndefined();
    expect(GradeResultSchema.parse({ ...base, matchedTier: null }).matchedTier).toBeNull();
    // "fail" is an internal ladder outcome and must never reach the client.
    expect(GradeResultSchema.safeParse({ ...base, matchedTier: "fail" }).success).toBe(false);
    expect(GradeResultSchema.safeParse({ ...base, matchedTier: "guessed" }).success).toBe(false);
    expect(
      SessionSummarySchema.parse({
        totalQuestions: 3,
        attempted: 3,
        correct: 2,
        missedCardIds: [7],
        revealedCardIds: [7],
        complete: true,
      }).complete,
    ).toBe(true);
  });
});
