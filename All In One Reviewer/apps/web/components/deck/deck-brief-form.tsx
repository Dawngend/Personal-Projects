"use client";

import type { UseFormRegister } from "react-hook-form";
import type { GenerationRequest } from "@/lib/contracts";

export function DeckBriefForm({
  register,
  errors,
}: {
  register: UseFormRegister<GenerationRequest>;
  errors: Partial<Record<keyof GenerationRequest, { message?: string }>>;
}) {
  return (
    <div className="brief-grid">
      <label>
        Deck name
        <input
          placeholder="Linear Algebra — Midterm 1"
          {...register("deckName")}
          aria-invalid={Boolean(errors.deckName)}
        />
      </label>
      <label>
        Subject
        <input
          placeholder="Linear Algebra"
          {...register("subject")}
          aria-invalid={Boolean(errors.subject)}
        />
      </label>
      <label className="question-count">
        Questions
        <input
          type="number"
          min="1"
          max="100"
          {...register("totalQuestions", { valueAsNumber: true })}
          aria-invalid={Boolean(errors.totalQuestions)}
        />
      </label>
      {(errors.deckName || errors.subject || errors.totalQuestions) && (
        <p className="form-error">
          {errors.deckName?.message ?? errors.subject?.message ?? errors.totalQuestions?.message}
        </p>
      )}
    </div>
  );
}
