from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = PROJECT_ROOT / "corpus" / "processed" / "faiss_index"

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def main():
    embeddings = HuggingFaceEmbeddings(
        model_name=MODEL_NAME,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )

    vector_store = FAISS.load_local(
        str(INDEX_DIR),
        embeddings,
        allow_dangerous_deserialization=True,
    )

    queries = [
        "What determines customer liability for an unauthorised electronic banking transaction?",
        "What happens when a customer reports an unauthorised transaction after seven working days?",
        "What is the RBI Integrated Ombudsman Scheme?",
    ]

    for query in queries:
        print("\n" + "=" * 80)
        print(f"QUERY: {query}")
        print("=" * 80)

        results = vector_store.similarity_search_with_score(query, k=3)

        for rank, (document, score) in enumerate(results, start=1):
            print(f"\nResult {rank}")
            print(f"Source: {document.metadata['source']}")
            print(f"Page: {document.metadata['page']}")
            print(f"Distance: {score:.4f}")
            print(f"Text: {document.page_content[:700]}")


if __name__ == "__main__":
    main()