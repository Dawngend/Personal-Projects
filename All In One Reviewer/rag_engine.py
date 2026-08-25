"""Subject-scoped Chroma course memory with lazy service initialization."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


DEFAULT_COLLECTION_NAME = "feu_modules"
DEFAULT_MEMORY_DIRECTORY = Path(
    os.environ.get(
        "ANDYHUB_COURSE_MEMORY_DIRECTORY",
        Path(__file__).resolve().parent / "course_brain_db",
    )
)


class CourseMemory:
    """One initialized Chroma collection shared by generation orchestration."""

    def __init__(self, collection: Any) -> None:
        self.collection = collection

    @classmethod
    def create(
        cls,
        memory_directory: str | os.PathLike[str] = DEFAULT_MEMORY_DIRECTORY,
        *,
        chroma_client: Any | None = None,
        embedding_function: Any | None = None,
    ) -> "CourseMemory":
        """Keep Chroma's existing persistent collection and default embedding model."""

        if chroma_client is None or embedding_function is None:
            import chromadb
            from chromadb.utils import embedding_functions

            chroma_client = chroma_client or chromadb.PersistentClient(path=str(memory_directory))
            embedding_function = embedding_function or embedding_functions.DefaultEmbeddingFunction()
        collection = chroma_client.get_or_create_collection(
            name=DEFAULT_COLLECTION_NAME,
            embedding_function=embedding_function,
        )
        return cls(collection)

    def add_to_memory(self, module_name: str, subject: str, chunks: list[str]) -> None:
        subject_clean = subject.strip().lower()
        print(f"\n  [Brain] Memorizing {len(chunks)} chunks for subject '{subject_clean}'...")
        ids = [f"{module_name}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"source": module_name, "subject": subject_clean} for _ in chunks]
        try:
            self.collection.upsert(documents=chunks, metadatas=metadatas, ids=ids)
            print("  [Brain] Memorization complete!")
        except Exception as exc:
            print(f"  [Brain Error] Failed to save to ChromaDB: {exc}")

    def get_historical_context(
        self, current_chunk: str, subject: str, n_results: int = 2
    ) -> str:
        subject_clean = subject.strip().lower()
        try:
            results = self.collection.query(
                query_texts=[current_chunk],
                n_results=n_results,
                where={"subject": subject_clean},
            )
            documents = results.get("documents", [[]])[0]
            sources = results.get("metadatas", [[{}]])[0]
            if not documents:
                return ""
            context_string = "\n\n--- PAST RELEVANT KNOWLEDGE (From Vector DB) ---\n"
            for document, metadata in zip(documents, sources):
                source_name = metadata.get("source", "Past Module")
                context_string += f"[{source_name}]: {document[:500]}...\n\n"
            return context_string
        except Exception as exc:
            print(f"  [Brain Warning] Vector search failed: {exc}")
            return ""


_course_memory: CourseMemory | None = None


def initialize_course_memory(
    memory_directory: str | os.PathLike[str] = DEFAULT_MEMORY_DIRECTORY,
    *,
    chroma_client: Any | None = None,
    embedding_function: Any | None = None,
) -> CourseMemory:
    """Initialize once; a future FastAPI lifespan calls this during startup."""

    global _course_memory
    if _course_memory is None:
        _course_memory = CourseMemory.create(
            memory_directory,
            chroma_client=chroma_client,
            embedding_function=embedding_function,
        )
    return _course_memory


def get_course_memory() -> CourseMemory:
    return initialize_course_memory()


# Backward-compatible functions used by the live Streamlit generator.
def add_to_memory(module_name: str, subject: str, chunks: list[str]) -> None:
    get_course_memory().add_to_memory(module_name, subject, chunks)


def get_historical_context(current_chunk: str, subject: str, n_results: int = 2) -> str:
    return get_course_memory().get_historical_context(current_chunk, subject, n_results)
