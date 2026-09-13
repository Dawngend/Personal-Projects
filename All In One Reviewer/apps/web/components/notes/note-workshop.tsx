"use client";

import Link from "next/link";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { GenerationTrace } from "@/components/generation/generation-trace";
import { ModuleShelf } from "@/components/deck/module-shelf";
import { api, subscribeToNoteGeneration } from "@/lib/api";
import { NoteRequestSchema, type NoteJob, type NoteRequest } from "@/lib/contracts";
import workshop from "@/components/deck/deck-workshop.module.css";
import styles from "./note-workshop.module.css";

const steps = ["Materials", "Note brief", "Depth", "Generate"];
const depths = [
  ["summary", "Summary", "Essential ideas and formulas for a fast review."],
  ["standard", "Standard", "Major ideas, terms, properties, and representative examples."],
  ["deep", "Deep", "Detailed explanations, edge cases, derivations, and worked examples."],
] as const;

type Props = {
  initialModuleIds: string[];
  initialSubject: string;
  initialTitle: string;
};

export function NoteWorkshop({ initialModuleIds, initialSubject, initialTitle }: Props) {
  const modules = useQuery({ queryKey: ["modules"], queryFn: api.listModules });
  const [selectedModuleIds, setSelectedModuleIds] = useState(initialModuleIds);
  const [job, setJob] = useState<NoteJob | null>(null);
  const form = useForm<NoteRequest>({
    resolver: zodResolver(NoteRequestSchema),
    defaultValues: {
      title: initialTitle,
      subject: initialSubject,
      moduleIds: initialModuleIds,
      depth: "standard",
    },
  });
  const generation = useMutation({ mutationFn: api.startNoteGeneration, onSuccess: setJob });

  useEffect(() => {
    form.setValue("moduleIds", selectedModuleIds, { shouldValidate: form.formState.isSubmitted });
  }, [form, selectedModuleIds]);

  useEffect(() => {
    if (!job || job.status === "complete" || job.status === "failed") return;
    return subscribeToNoteGeneration(
      job.id,
      setJob,
      () =>
        void api
          .getNoteGeneration(job.id)
          .then(setJob)
          .catch(() => undefined),
    );
  }, [job?.id, job?.status]);

  const submit = form.handleSubmit((values) =>
    generation.mutate({ ...values, moduleIds: selectedModuleIds }),
  );
  const busy = generation.isPending || job?.status === "queued" || job?.status === "running";
  const errors = form.formState.errors;

  return (
    <main className={workshop.page}>
      <header className={workshop.header}>
        <Link href="/" className={workshop.wordmark}>
          Andy<span>Hub</span>
        </Link>
        <Link href="/notes" className={workshop.back}>
          ← Notes library
        </Link>
      </header>
      <div className={workshop.intro}>
        <p className="eyebrow">Generated notes</p>
        <h1>
          Shape the material.
          <br />
          Keep the reviewer.
        </h1>
        <p>
          Andy turns selected modules into structured notes that stay separate from flashcard decks
          and print cleanly from the browser.
        </p>
      </div>
      <nav className={workshop.steps} aria-label="Note generation stages">
        {steps.map((step, index) => (
          <span key={step}>
            <b>{String(index + 1).padStart(2, "0")}</b>
            {step}
          </span>
        ))}
      </nav>
      <div className={workshop.workbench}>
        <GenerationTrace
          job={job}
          modules={modules.data ?? []}
          selectedModuleIds={selectedModuleIds}
          variant="note"
        />
        <form className={workshop.form} onSubmit={submit}>
          <section>
            <div className={workshop.sectionHead}>
              <p className="eyebrow">01 · Materials</p>
              <h2>Choose the source modules</h2>
              <p>Select one or more existing PDFs or slide decks for this written reviewer.</p>
            </div>
            {modules.isLoading && <p className="truthful-status">Reading uploaded modules…</p>}
            {modules.isError && <p className="form-error">The module library could not load.</p>}
            <ModuleShelf
              modules={modules.data ?? []}
              selected={selectedModuleIds}
              onChange={setSelectedModuleIds}
            />
            {errors.moduleIds && <p className="form-error">{errors.moduleIds.message}</p>}
            {!modules.isLoading && modules.data?.length === 0 && (
              <p className={styles.uploadHint}>
                No modules are uploaded yet. <Link href="/decks/new">Upload materials</Link> in the
                deck workshop first.
              </p>
            )}
          </section>
          <section>
            <div className={workshop.sectionHead}>
              <p className="eyebrow">02 · Note brief</p>
              <h2>Name the written reviewer</h2>
              <p>The subject also scopes retrieval to matching course memory.</p>
            </div>
            <div className={styles.briefGrid}>
              <label>
                Note title
                <input {...form.register("title")} placeholder="Linear Algebra review notes" />
                {errors.title && <span className="form-error">{errors.title.message}</span>}
              </label>
              <label>
                Subject
                <input {...form.register("subject")} placeholder="Linear Algebra" />
                {errors.subject && <span className="form-error">{errors.subject.message}</span>}
              </label>
            </div>
          </section>
          <section>
            <div className={workshop.sectionHead}>
              <p className="eyebrow">03 · Depth</p>
              <h2>Set the level of detail</h2>
              <p>Depth changes the note-writing brief, not the source material.</p>
            </div>
            <div className={styles.depthGrid}>
              {depths.map(([value, label, description]) => (
                <label key={value}>
                  <input type="radio" value={value} {...form.register("depth")} />
                  <strong>{label}</strong>
                  <small>{description}</small>
                </label>
              ))}
            </div>
          </section>
          <section className={workshop.generate}>
            <div>
              <p className="eyebrow">04 · Generate</p>
              <h2>Make these notes</h2>
              <p>
                {selectedModuleIds.length
                  ? `${selectedModuleIds.length} selected module${selectedModuleIds.length === 1 ? "" : "s"} will become a separate written reviewer.`
                  : "Choose one or more modules before generating."}
              </p>
            </div>
            <button className={workshop.generateButton} type="submit" disabled={busy}>
              {busy ? "Generation in progress" : "Generate notes →"}
            </button>
          </section>
          {generation.isError && <p className="form-error">{generation.error.message}</p>}
          {job?.status === "complete" && job.noteId && (
            <p className={workshop.complete}>
              Notes ready. <Link href={`/notes/${job.noteId}`}>Open and print them</Link>.
            </p>
          )}
        </form>
      </div>
    </main>
  );
}
