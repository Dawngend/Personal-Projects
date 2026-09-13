import { NoteWorkshop } from "@/components/notes/note-workshop";

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

export default async function NewNotePage({ searchParams }: { searchParams: SearchParams }) {
  const query = await searchParams;
  const rawModuleIds = typeof query.moduleIds === "string" ? query.moduleIds : "";
  return (
    <NoteWorkshop
      initialModuleIds={rawModuleIds.split(",").filter(Boolean)}
      initialSubject={typeof query.subject === "string" ? query.subject : ""}
      initialTitle={typeof query.title === "string" ? query.title : ""}
    />
  );
}
