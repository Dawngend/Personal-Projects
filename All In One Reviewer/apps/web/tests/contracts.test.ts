import { describe, expect, it } from "vitest";
import { GenerationJobSchema, QuizCardSchema } from "../lib/contracts";

describe("Phase 2 API client contract", () => {
  it("accepts the safe discriminated quiz-card payloads and rejects answer keys", () => {
    expect(QuizCardSchema.parse({ id: 1, type: "multiple_choice", question: "Q", options: ["A", "B"] }).type).toBe("multiple_choice");
    expect(QuizCardSchema.parse({ id: 2, type: "enumeration", question: "Q", expectedCount: 3 }).type).toBe("enumeration");
    expect(QuizCardSchema.safeParse({ id: 3, type: "problem", question: "Q", correctAnswer: "24" }).success).toBe(false);
  });

  it("matches the persisted worker status contract used by SSE", () => {
    expect(GenerationJobSchema.parse({ id: "gen_abc", status: "running", stage: "generating", progress: 62, message: "Generating questions from module chunk 3 of 5", cardsReceived: 12, cardsValid: 10, deckId: null, error: null }).progress).toBe(62);
  });
});
