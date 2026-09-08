"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, moduleFileUrl, streamChatReply } from "@/lib/api";
import type { ChatAction, ChatMessage } from "@/lib/contracts";
import { PdfViewer } from "@/components/reviewer/pdf-viewer";
import styles from "./reviewer-view.module.css";

type LiveMessage = Pick<ChatMessage, "role" | "content"> & { id: string };

const QUICK_ACTIONS: { action: ChatAction; label: string }[] = [
  { action: "explain", label: "Explain the difficult parts" },
  { action: "summarize", label: "Add a summary at the top" },
  { action: "fill_gaps", label: "Fill in the gaps" },
];

export function ReviewerView({ moduleId }: { moduleId: string }) {
  const modules = useQuery({ queryKey: ["modules"], queryFn: api.listModules });
  const history = useQuery({
    queryKey: ["module-chat", moduleId],
    queryFn: () => api.getModuleChat(moduleId),
  });
  const [liveMessages, setLiveMessages] = useState<LiveMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const module_ = modules.data?.find((item) => item.id === moduleId);
  const persisted: LiveMessage[] = history.data ?? [];
  const messages = [...persisted, ...liveMessages];

  function send(text: string, action?: ChatAction) {
    const trimmed = text.trim();
    if (!trimmed || isStreaming) return;
    setStreamError(null);
    setInput("");
    setIsStreaming(true);
    const assistantId = `live_${Date.now()}`;
    setLiveMessages([
      { id: `live_${Date.now()}_user`, role: "user", content: trimmed },
      { id: assistantId, role: "assistant", content: "" },
    ]);
    void streamChatReply(
      moduleId,
      trimmed,
      action,
      (delta) =>
        setLiveMessages((current) =>
          current.map((message) =>
            message.id === assistantId ? { ...message, content: message.content + delta } : message,
          ),
        ),
      () => {
        setIsStreaming(false);
        void history.refetch().then(() => setLiveMessages([]));
      },
      (error) => {
        setIsStreaming(false);
        setStreamError(error.message);
      },
    );
  }

  if (modules.isLoading || history.isLoading)
    return <main className={styles.state}>Opening the reviewer…</main>;

  if (!module_)
    return (
      <main className={styles.state}>
        <p className="eyebrow">Module unavailable</p>
        <h1>Andy could not find this module.</h1>
        <Link href="/">Return to library</Link>
      </main>
    );

  const isPdf = module_.mediaType === "application/pdf";

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" className={styles.wordmark}>
          Andy<span>Hub</span>
        </Link>
        <Link href="/" className={styles.back}>
          ← Study workspace
        </Link>
      </header>
      <p className="eyebrow">Reviewer</p>
      <h1 className={styles.title}>{module_.filename}</h1>
      <div className={styles.split}>
        <section className={styles.sourcePane}>
          {isPdf ? (
            <PdfViewer url={moduleFileUrl(moduleId)} />
          ) : (
            <p className={styles.noPreview}>
              No inline preview for this file type yet — ask the tutor about its content instead.
            </p>
          )}
        </section>
        <section className={styles.chatPane}>
          <div className={styles.quickActions}>
            {QUICK_ACTIONS.map(({ action, label }) => (
              <button
                key={action}
                type="button"
                disabled={isStreaming}
                onClick={() => send(label, action)}
              >
                {label}
              </button>
            ))}
          </div>
          <ol className={styles.messages}>
            {messages.length === 0 && (
              <p className={styles.emptyState}>
                Ask Andy anything about this module, or start with a quick action above.
              </p>
            )}
            {messages.map((message) => (
              <li key={message.id} className={message.role === "user" ? styles.userMessage : styles.assistantMessage}>
                {message.content || (isStreaming ? "…" : "")}
              </li>
            ))}
          </ol>
          {streamError && (
            <p className={styles.chatError} role="alert">
              {streamError}
            </p>
          )}
          <form
            className={styles.composer}
            onSubmit={(event) => {
              event.preventDefault();
              send(input);
            }}
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask about this module…"
              disabled={isStreaming}
            />
            <button type="submit" disabled={isStreaming || !input.trim()}>
              Send
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
