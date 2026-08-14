"use client";

import { motion, useReducedMotion } from "framer-motion";
import type { GenerationJob, ModuleItem } from "@/lib/contracts";

const stages = [
  ["queued", "Queued", "Waiting for the local generation worker."],
  ["extracting", "Extracting", "Reading selected PDF and slide-deck content."],
  ["retrieving_memory", "Connecting memory", "Looking up relevant material in this subject."],
  ["generating", "Generating", "Requesting question candidates from the study engine."],
  ["validating", "Validating", "Checking card structure before saving anything."],
  ["saving", "Saving", "Writing a complete deck and its cards to the library."],
  ["complete", "Ready", "Deck generation is complete."],
] as const;

type Props = { job: GenerationJob | null; modules: ModuleItem[]; selectedModuleIds: string[]; totalQuestions: number };

export function GenerationTrace({ job, modules, selectedModuleIds, totalQuestions }: Props) {
  const reducedMotion = useReducedMotion();
  const activeIndex = job ? stages.findIndex(([stage]) => stage === job.stage) : -1;
  const selected = modules.filter((module) => selectedModuleIds.includes(module.id));
  const detail = job?.stage === "validating" && job.cardsValid > 0 ? `Validating ${job.cardsValid} of ${totalQuestions} cards` : job?.message;
  return <aside className="reasoning-gutter" aria-live="polite" aria-label="Generation progress">
    <p className="gutter-title">Reasoning trace</p>
    <div className="source-nodes">{selected.length ? selected.map((module) => <div className="source-node" key={module.id}><i aria-hidden="true" /> <span>{module.filename}</span></div>) : <p className="gutter-quiet">Select source modules to start a trace.</p>}</div>
    <ol>{stages.map(([stage, title, fallback], index) => {
      const state = !job ? "idle" : job.status === "failed" ? (stage === "complete" ? "idle" : index <= activeIndex ? "complete" : "idle") : index < activeIndex ? "complete" : index === activeIndex ? "active" : "idle";
      return <motion.li key={stage} className={`trace-${state}`} initial={false} animate={reducedMotion ? {} : { opacity: state === "idle" ? .55 : 1, x: state === "active" ? 2 : 0 }} transition={{ duration: .24, ease: "easeOut" }}><i aria-hidden="true" /><div><strong>{title}</strong>{state === "active" && <small>{detail ?? fallback}</small>}</div></motion.li>;
    })}</ol>
    {job?.status === "failed" && <p className="trace-failure">{job.error ?? "Generation could not complete."}</p>}
  </aside>;
}
