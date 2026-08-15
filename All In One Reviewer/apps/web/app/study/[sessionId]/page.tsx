import { StudySession } from "@/components/study/study-session";

export default async function StudyPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <StudySession sessionId={sessionId} />;
}
