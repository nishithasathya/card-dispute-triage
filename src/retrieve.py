import json
from pathlib import Path

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHUNKS_FILE = PROJECT_ROOT / "corpus" / "processed" / "chunks.json"
INDEX_DIR = PROJECT_ROOT / "corpus" / "processed" / "faiss_index"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def load_chunks():
    with CHUNKS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def main():
    chunks = load_chunks()

    if not chunks:
        raise ValueError("No chunks found. Run src/ingest.py first.")

    documents = [
        Document(
            page_content=chunk["text"],
            metadata={
                "chunk_id": chunk["chunk_id"],
                "source": chunk["source"],
                "page": chunk["page"],
            },
        )
        for chunk in chunks
    ]

    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    vector_store = FAISS.from_documents(documents, embeddings)

    INDEX_DIR.parent.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(INDEX_DIR))

    print(f"Indexed chunks: {len(documents)}")
    print(f"Embedding model: {MODEL_NAME}")
    print(f"Index saved to: {INDEX_DIR}")


if __name__ == "__main__":
    main()