"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { api, subscribeToGeneration } from "@/lib/api";
import { GenerationRequestSchema, type GenerationJob, type GenerationRequest } from "@/lib/contracts";
import { DeckBriefForm } from "./deck-brief-form";
import { ModuleDropzone } from "./module-dropzone";
import { ModuleShelf } from "./module-shelf";
import { QuestionStyleField } from "./question-style-field";
import { GenerationTrace } from "@/components/generation/generation-trace";
import styles from "./deck-workshop.module.css";

const steps = ["Materials", "Deck brief", "Question style", "Generate"];

export function DeckWorkshop() {
  const queryClient = useQueryClient();
  const modules = useQuery({ queryKey: ["modules"], queryFn: api.listModules });
  const [selectedModuleIds, setSelectedModuleIds] = useState<string[]>([]);
  const [job, setJob] = useState<GenerationJob | null>(null);
  const form = useForm<GenerationRequest>({ resolver: zodResolver(GenerationRequestSchema), defaultValues: { deckName: "", subject: "", moduleIds: [], questionStyle: "mixed", totalQuestions: 20 } });
  const upload = useMutation({ mutationFn: api.uploadModules, onSuccess: (newModules) => { queryClient.invalidateQueries({ queryKey: ["modules"] }); setSelectedModuleIds((current) => [...new Set([...current, ...newModules.map((module) => module.id)])]); } });
  const generation = useMutation({ mutationFn: api.startGeneration, onSuccess: setJob });
  const totalQuestions = form.watch("totalQuestions") || 20;

  useEffect(() => {
    form.setValue("moduleIds", selectedModuleIds, { shouldValidate: form.formState.isSubmitted });
  }, [form, selectedModuleIds]);

  useEffect(() => {
    if (!job || job.status === "complete" || job.status === "failed") return;
    return subscribeToGeneration(job.id, setJob, () => void api.getGeneration(job.id).then(setJob).catch(() => undefined));
  }, [job?.id, job?.status]);

  const submit = form.handleSubmit((values) => generation.mutate({ ...values, moduleIds: selectedModuleIds }));
  const errors = form.formState.errors;
  return <main className={styles.page}>
    <header className={styles.header}><Link href="/" className={styles.wordmark}>Andy<span>Hub</span></Link><Link href="/" className={styles.back}>← Study workspace</Link></header>
    <div className={styles.intro}><p className="eyebrow">Deck workshop</p><h1>Plant the material.<br />Trace the reasoning.</h1><p>Andy builds a reviewer only from the modules you choose, then reports the generation path as it actually happens.</p></div>
    <nav className={styles.steps} aria-label="Deck generation stages">{steps.map((step, index) => <span key={step}><b>{String(index + 1).padStart(2, "0")}</b>{step}</span>)}</nav>
    <div className={styles.workbench}><GenerationTrace job={job} modules={modules.data ?? []} selectedModuleIds={selectedModuleIds} totalQuestions={totalQuestions} />
      <form className={styles.form} onSubmit={submit}>
        <section><div className={styles.sectionHead}><p className="eyebrow">01 · Materials</p><h2>Choose the source modules</h2><p>Upload course PDFs or slide decks. Existing uploads stay available for future decks.</p></div><ModuleDropzone disabled={upload.isPending} onFiles={(files) => files.length && upload.mutate(files)} />{upload.isPending && <p className="truthful-status">Uploading selected files…</p>}{upload.isError && <p className="form-error">{upload.error.message}</p>}<ModuleShelf modules={modules.data ?? []} selected={selectedModuleIds} onChange={setSelectedModuleIds} />{errors.moduleIds && <p className="form-error">{errors.moduleIds.message}</p>}</section>
        <section><div className={styles.sectionHead}><p className="eyebrow">02 · Deck brief</p><h2>Frame the review</h2><p>Give the material a useful name, subject, and deliberate amount of practice.</p></div><DeckBriefForm register={form.register} errors={errors} /></section>
        <section><div className={styles.sectionHead}><p className="eyebrow">03 · Question style</p><h2>Set the recall mode</h2><p>Mixed is the default: exact choices, full enumerations, and final-answer problems.</p></div><QuestionStyleField register={form.register} /></section>
        <section className={styles.generate}><div><p className="eyebrow">04 · Generate</p><h2>Make this deck</h2><p>{selectedModuleIds.length ? `${selectedModuleIds.length} selected module${selectedModuleIds.length === 1 ? "" : "s"} will be sent to the generation worker.` : "Choose one or more modules before generating."}</p></div><button className={styles.generateButton} type="submit" disabled={generation.isPending || job?.status === "running"}>{generation.isPending ? "Queueing generation…" : job?.status === "running" ? "Generation in progress" : "Generate deck →"}</button></section>
        {generation.isError && <p className="form-error">{generation.error.message}</p>}{job?.status === "complete" && job.deckId && <p className={styles.complete}>Deck ready. <Link href={`/decks/${job.deckId}`}>Open this deck</Link> to begin studying.</p>}
      </form>
    </div>
  </main>;
}
