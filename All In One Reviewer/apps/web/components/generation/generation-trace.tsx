"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { GenerationJob, ModuleItem, NoteJob } from "@/lib/contracts";

const traces = {
  deck: [
    ["queued", "Queued", "Waiting for the local generation worker."],
    ["extracting", "Extracting", "Reading selected PDF and slide-deck content."],
    ["retrieving_memory", "Connecting memory", "Looking up relevant material in this subject."],
    ["generating", "Generating", "Requesting question candidates from the study engine."],
    ["validating", "Validating", "Checking card structure before saving anything."],
    ["saving", "Saving", "Writing a complete deck and its cards to the library."],
    ["complete", "Ready", "Deck generation is complete."],
  ],
  note: [
    ["queued", "Queued", "Waiting for the local generation worker."],
    ["extracting", "Extracting", "Reading selected PDF and slide-deck content."],
    ["retrieving_memory", "Connecting memory", "Looking up relevant material in this subject."],
    ["generating", "Drafting", "Building structured study-note sections."],
    ["validating", "Validating", "Checking every section before saving anything."],
    ["saving", "Saving", "Writing the printable notes to the notes library."],
    ["complete", "Ready", "Generated notes are ready to review or print."],
  ],
} as const;

type Props = {
  job: GenerationJob | NoteJob | null;
  modules: ModuleItem[];
  selectedModuleIds: string[];
  totalQuestions?: number;
  variant?: "deck" | "note";
};

export function GenerationTrace({
  job,
  modules,
  selectedModuleIds,
  totalQuestions = 0,
  variant = "deck",
}: Props) {
  const stages = traces[variant];
  const reducedMotion = useReducedMotion();
  const activeIndex = job ? stages.findIndex(([stage]) => stage === job.stage) : -1;
  const selected = modules.filter((module) => selectedModuleIds.includes(module.id));
  const detail =
    job?.stage === "validating" && "cardsValid" in job && job.cardsValid > 0
      ? `Validating ${job.cardsValid} of ${totalQuestions} cards`
      : job?.message;
  return (
    <aside className="reasoning-gutter" aria-live="polite" aria-label="Generation progress">
      <p className="gutter-title">Reasoning trace</p>
      <div className="source-nodes">
        {selected.length ? (
          selected.map((module) => (
            <div className="source-node" key={module.id}>
              <i aria-hidden="true" /> <span>{module.filename}</span>
            </div>
          ))
        ) : (
          <p className="gutter-quiet">Select source modules to start a trace.</p>
        )}
      </div>
      <ol>
        {stages.map(([stage, title, fallback], index) => {
          const state = !job
            ? "idle"
            : job.status === "failed"
              ? stage === "complete"
                ? "idle"
                : index <= activeIndex
                  ? "complete"
                  : "idle"
              : index < activeIndex
                ? "complete"
                : index === activeIndex
                  ? "active"
                  : "idle";
          return (
            <motion.li
              key={stage}
              className={`trace-${state}`}
              initial={false}
              animate={
                reducedMotion
                  ? {}
                  : { opacity: state === "idle" ? 0.55 : 1, x: state === "active" ? 2 : 0 }
              }
              transition={{ duration: 0.24, ease: "easeOut" }}
            >
              <i aria-hidden="true" />
              <div>
                <strong>{title}</strong>
                {state === "active" && <small>{detail ?? fallback}</small>}
              </div>
            </motion.li>
          );
        })}
      </ol>
      {job?.status === "failed" && (
        <p className="trace-failure">{job.error ?? "Generation could not complete."}</p>
      )}
    </aside>
  );
}
