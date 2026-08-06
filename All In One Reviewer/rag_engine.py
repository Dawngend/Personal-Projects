import os
import chromadb
from chromadb.utils import embedding_functions

# Initialize a local persistent database folder
DB_DIR = os.path.join(os.getcwd(), "course_brain_db")
chroma_client = chromadb.PersistentClient(path=DB_DIR)

# Use Chroma's default sentence-transformers model
sentence_transformer_ef = embedding_functions.DefaultEmbeddingFunction()

# Create or load our memory collection
collection = chroma_client.get_or_create_collection(
    name="feu_modules",
    embedding_function=sentence_transformer_ef
)

def add_to_memory(module_name: str, subject: str, chunks: list[str]):
    """Embeds and saves module chunks into the vector database, tagged by subject."""
    subject_clean = subject.strip().lower()
    print(f"\n  [Brain] Memorizing {len(chunks)} chunks for subject '{subject_clean}'...")
    
    ids = [f"{module_name}_chunk_{i}" for i in range(len(chunks))]
    # Tag every chunk with its specific subject!
    metadatas = [{"source": module_name, "subject": subject_clean} for _ in chunks]
    
    try:
        collection.upsert(
            documents=chunks,
            metadatas=metadatas,
            ids=ids
        )
        print("  [Brain] Memorization complete!")
    except Exception as e:
        print(f"  [Brain Error] Failed to save to ChromaDB: {e}")

def get_historical_context(current_chunk: str, subject: str, n_results: int = 2) -> str:
    """Searches past modules ONLY within the requested subject."""
    subject_clean = subject.strip().lower()
    try:
        # The 'where' clause forces ChromaDB to only search matching subjects
        results = collection.query(
            query_texts=[current_chunk],
            n_results=n_results,
            where={"subject": subject_clean} 
        )
        
        documents = results.get("documents", [[]])[0]
        sources = results.get("metadatas", [[{}]])[0]
        
        if not documents:
            return ""
            
        context_string = "\n\n--- PAST RELEVANT KNOWLEDGE (From Vector DB) ---\n"
        for doc, meta in zip(documents, sources):
            source_name = meta.get("source", "Past Module")
            context_string += f"[{source_name}]: {doc[:500]}...\n\n"
            
        return context_string
    except Exception as e:
        print(f"  [Brain Warning] Vector search failed: {e}")
        return ""