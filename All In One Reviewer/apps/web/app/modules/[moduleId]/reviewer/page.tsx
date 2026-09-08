import { ReviewerView } from "@/components/reviewer/reviewer-view";

export default async function ReviewerPage({ params }: { params: Promise<{ moduleId: string }> }) {
  const { moduleId } = await params;
  return <ReviewerView moduleId={moduleId} />;
}
