import { NoteDetailView } from "@/components/notes/note-detail";

export default async function NoteDetailPage({ params }: { params: Promise<{ noteId: string }> }) {
  const { noteId } = await params;
  return <NoteDetailView noteId={Number(noteId)} />;
}
