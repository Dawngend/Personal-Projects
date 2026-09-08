import {
  type ChatAction,
  ChatMessageSchema,
  type ChatMessage,
  DeckDetailSchema,
  DeckSchema,
  type DeckSummary,
  GenerationJobSchema,
  type GenerationJob,
  type GenerationRequest,
  GradeResultSchema,
  type GradeResult,
  ModuleSchema,
  type ModuleItem,
  QuizSessionSchema,
  type QuizSession,
  RevealResultSchema,
  type RevealResult,
  SessionSummarySchema,
  type SessionSummary,
} from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  parse?: (value: unknown) => T,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(body?.error?.message ?? "AndyHub API is unavailable.", response.status);
  return parse ? parse(body) : (body as T);
}

export const api = {
  listModules: () =>
    request("/modules", undefined, (body) =>
      (body as { items: unknown[] }).items.map((item) => ModuleSchema.parse(item)),
    ),
  uploadModules: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request("/modules", { method: "POST", body: form }, (body) =>
      (body as { items: unknown[] }).items.map((item) => ModuleSchema.parse(item)),
    );
  },
  listDecks: () =>
    request("/decks", undefined, (body) =>
      (body as unknown[]).map((item) => DeckSchema.parse(item)),
    ),
  getDeck: (deckId: number) =>
    request(`/decks/${deckId}?include=cards`, undefined, (body) => DeckDetailSchema.parse(body)),
  startGeneration: (payload: GenerationRequest) =>
    request(
      "/generation-jobs",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      (body) => GenerationJobSchema.parse(body),
    ),
  getGeneration: (jobId: string) =>
    request(`/generation-jobs/${jobId}`, undefined, (body) => GenerationJobSchema.parse(body)),
  startSession: (deckId: number, mode: "all" | "missed") =>
    request(
      "/quiz-sessions",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deckId, mode }),
      },
      (body) => QuizSessionSchema.parse(body),
    ),
  getSession: (sessionId: string) =>
    request(`/quiz-sessions/${sessionId}`, undefined, (body) => QuizSessionSchema.parse(body)),
  submitAnswer: (
    sessionId: string,
    cardId: number,
    answer: { type: "multiple_choice" | "enumeration" | "problem"; value: string },
  ) =>
    request(
      `/quiz-sessions/${sessionId}/answers`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cardId, answer }),
      },
      (body) => GradeResultSchema.parse(body),
    ),
  revealSolution: (sessionId: string, cardId: number) =>
    request(
      `/quiz-sessions/${sessionId}/cards/${cardId}/reveal-solution`,
      { method: "POST" },
      (body) => RevealResultSchema.parse(body),
    ),
  advanceSession: (sessionId: string) =>
    request(`/quiz-sessions/${sessionId}/advance`, { method: "POST" }, (body) =>
      QuizSessionSchema.parse(body),
    ),
  getSessionSummary: (sessionId: string) =>
    request(`/quiz-sessions/${sessionId}/summary`, undefined, (body) =>
      SessionSummarySchema.parse(body),
    ),
  getModuleChat: (moduleId: string) =>
    request(`/modules/${moduleId}/chat`, undefined, (body) =>
      (body as unknown[]).map((item) => ChatMessageSchema.parse(item)),
    ),
};

export function moduleFileUrl(moduleId: string): string {
  return `${API_BASE}/modules/${moduleId}/file`;
}

/**
 * Chat replies stream over a POST'd SSE body, which EventSource cannot send —
 * read the response stream by hand instead, splitting on the same
 * "event: <name>\ndata: <json>\n\n" framing the backend already emits.
 */
export async function streamChatReply(
  moduleId: string,
  message: string,
  action: ChatAction | undefined,
  onToken: (delta: string) => void,
  onDone: () => void,
  onError: (error: Error) => void,
): Promise<void> {
  try {
    const response = await fetch(`${API_BASE}/modules/${moduleId}/chat/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, action }),
    });
    if (!response.ok || !response.body) {
      const body = await response.json().catch(() => null);
      throw new ApiError(body?.error?.message ?? "AndyHub API is unavailable.", response.status);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";
      for (const raw of events) {
        const eventName = raw.match(/^event: (.+)$/m)?.[1];
        const data = raw.match(/^data: (.+)$/m)?.[1];
        if (eventName === "token" && data) onToken((JSON.parse(data) as { delta: string }).delta);
        if (eventName === "done") onDone();
      }
    }
  } catch (error) {
    onError(error instanceof Error ? error : new Error("Chat stream failed."));
  }
}

export function subscribeToGeneration(
  jobId: string,
  onJob: (job: GenerationJob) => void,
  onError: () => void,
): () => void {
  const events = new EventSource(`${API_BASE}/generation-jobs/${jobId}/events`);
  events.addEventListener("progress", (event) =>
    onJob(GenerationJobSchema.parse(JSON.parse((event as MessageEvent).data))),
  );
  events.onerror = onError;
  return () => events.close();
}

export type {
  DeckSummary,
  ModuleItem,
  GradeResult,
  QuizSession,
  RevealResult,
  SessionSummary,
  ChatMessage,
  ChatAction,
};
