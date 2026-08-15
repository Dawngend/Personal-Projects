import { DeckDetail } from "@/components/deck/deck-detail";

export default async function DeckDetailPage({ params }: { params: Promise<{ deckId: string }> }) {
  const { deckId } = await params;
  const id = Number(deckId);
  if (!Number.isInteger(id) || id < 1) throw new Error("Invalid deck identifier.");
  return <DeckDetail deckId={id} />;
}
