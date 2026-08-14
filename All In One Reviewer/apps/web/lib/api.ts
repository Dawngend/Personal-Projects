import { DeckSchema, type DeckSummary, GenerationJobSchema, type GenerationJob, type GenerationRequest, ModuleSchema, type ModuleItem } from "@/lib/contracts";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(path: string, init?: RequestInit, parse?: (value: unknown) => T): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers: { Accept: "application/json", ...init?.headers } });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(body?.error?.message ?? "AndyHub API is unavailable.", response.status);
  return parse ? parse(body) : body as T;
}

export const api = {
  listModules: () => request("/modules", undefined, (body) => (body as { items: unknown[] }).items.map((item) => ModuleSchema.parse(item))),
  uploadModules: (files: File[]) => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request("/modules", { method: "POST", body: form }, (body) => (body as { items: unknown[] }).items.map((item) => ModuleSchema.parse(item)));
  },
  listDecks: () => request("/decks", undefined, (body) => (body as unknown[]).map((item) => DeckSchema.parse(item))),
  startGeneration: (payload: GenerationRequest) => request("/generation-jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }, (body) => GenerationJobSchema.parse(body)),
  getGeneration: (jobId: string) => request(`/generation-jobs/${jobId}`, undefined, (body) => GenerationJobSchema.parse(body)),
};

export function subscribeToGeneration(jobId: string, onJob: (job: GenerationJob) => void, onError: () => void): () => void {
  const events = new EventSource(`${API_BASE}/generation-jobs/${jobId}/events`);
  events.addEventListener("progress", (event) => onJob(GenerationJobSchema.parse(JSON.parse((event as MessageEvent).data))));
  events.onerror = onError;
  return () => events.close();
}

export type { DeckSummary, ModuleItem };
