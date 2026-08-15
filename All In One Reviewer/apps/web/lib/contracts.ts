import { z } from "zod";

/** Hand-written client contract verified by Phase 2's FastAPI OpenAPI test. */
export const QuestionStyleSchema = z.enum(["multiple_choice", "enumeration", "problem", "mixed"]);
export type QuestionStyle = z.infer<typeof QuestionStyleSchema>;

export const ModuleSchema = z.object({
  id: z.string().startsWith("mod_"),
  filename: z.string(),
  mediaType: z.string(),
  sizeBytes: z.number().int().nonnegative(),
  contentHash: z.string().startsWith("sha256:"),
  extractionStatus: z.enum(["pending", "ready", "failed"]),
  duplicate: z.boolean().default(false),
});
export type ModuleItem = z.infer<typeof ModuleSchema>;

export const DeckSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  subject: z.string(),
  modules: z.array(z.string()),
  cardCount: z.number().int(),
  questionTypes: z.record(z.string(), z.number().int()),
  totalMisses: z.number().int(),
});
export type DeckSummary = z.infer<typeof DeckSchema>;

export const GenerationJobSchema = z.object({
  id: z.string().startsWith("gen_"),
  status: z.enum(["queued", "running", "complete", "failed"]),
  stage: z.enum(["queued", "extracting", "retrieving_memory", "generating", "validating", "saving", "complete", "failed"]),
  progress: z.number().min(0).max(100),
  message: z.string().nullable().optional(),
  cardsReceived: z.number().int(),
  cardsValid: z.number().int(),
  deckId: z.number().int().nullable().optional(),
  error: z.string().nullable().optional(),
});
export type GenerationJob = z.infer<typeof GenerationJobSchema>;

const MultipleChoiceCard = z.object({ id: z.number(), type: z.literal("multiple_choice"), question: z.string(), options: z.array(z.string()) }).strict();
const EnumerationCard = z.object({ id: z.number(), type: z.literal("enumeration"), question: z.string(), expectedCount: z.number().int() }).strict();
const ProblemCard = z.object({ id: z.number(), type: z.literal("problem"), question: z.string(), answerFormatHint: z.string().nullable().optional() }).strict();
export const QuizCardSchema = z.discriminatedUnion("type", [MultipleChoiceCard, EnumerationCard, ProblemCard]);
export type QuizCard = z.infer<typeof QuizCardSchema>;

export const DeckDetailSchema = DeckSchema.extend({ cards: z.array(QuizCardSchema).nullable().optional() });
export type DeckDetail = z.infer<typeof DeckDetailSchema>;

export const QuizSessionSchema = z.object({
  id: z.string().startsWith("quiz_"),
  deck: z.object({ id: z.number().int(), name: z.string() }),
  totalQuestions: z.number().int().nonnegative(),
  currentIndex: z.number().int().nonnegative(),
  card: QuizCardSchema.nullable(),
  complete: z.boolean(),
}).strict();
export type QuizSession = z.infer<typeof QuizSessionSchema>;

/** Answer-key fields exist only in post-grade or explicit reveal responses. */
export const GradeResultSchema = z.object({
  correct: z.boolean(), complete: z.boolean(), feedback: z.string(),
  caughtItems: z.array(z.string()).nullable().optional(),
  missedItems: z.array(z.string()).nullable().optional(),
  expectedAnswer: z.string().nullable().optional(),
  solutionSteps: z.array(z.string()).nullable().optional(),
}).strict();
export type GradeResult = z.infer<typeof GradeResultSchema>;

export const RevealResultSchema = z.object({ expectedAnswer: z.string(), solutionSteps: z.array(z.string()) }).strict();
export type RevealResult = z.infer<typeof RevealResultSchema>;

export const SessionSummarySchema = z.object({
  totalQuestions: z.number().int().nonnegative(), attempted: z.number().int().nonnegative(), correct: z.number().int().nonnegative(),
  missedCardIds: z.array(z.number().int()), revealedCardIds: z.array(z.number().int()), complete: z.boolean(),
}).strict();
export type SessionSummary = z.infer<typeof SessionSummarySchema>;

export const GenerationRequestSchema = z.object({
  deckName: z.string().trim().min(2, "Name the deck."),
  subject: z.string().trim().min(2, "Add a subject."),
  moduleIds: z.array(z.string().startsWith("mod_")).min(1, "Choose at least one module."),
  questionStyle: QuestionStyleSchema,
  totalQuestions: z.number().int().min(1).max(100),
});
export type GenerationRequest = z.infer<typeof GenerationRequestSchema>;
