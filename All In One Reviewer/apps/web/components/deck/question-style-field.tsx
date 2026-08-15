"use client";

import type { UseFormRegister } from "react-hook-form";
import type { GenerationRequest, QuestionStyle } from "@/lib/contracts";

const styles: { value: QuestionStyle; title: string; copy: string }[] = [
  { value: "multiple_choice", title: "Multiple choice", copy: "Choose one exact option." },
  { value: "enumeration", title: "Enumeration", copy: "Recall every expected item." },
  { value: "problem", title: "Problem-solving", copy: "Work toward a final answer." },
  { value: "mixed", title: "Mixed", copy: "Use all three question forms." },
];

export function QuestionStyleField({ register }: { register: UseFormRegister<GenerationRequest> }) {
  return (
    <div className="style-grid">
      {styles.map((style) => (
        <label key={style.value} className="style-option">
          <input type="radio" value={style.value} {...register("questionStyle")} />
          <span>
            <strong>{style.title}</strong>
            <small>{style.copy}</small>
          </span>
        </label>
      ))}
    </div>
  );
}
