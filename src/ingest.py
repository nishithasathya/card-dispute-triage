import json
from pathlib import Path

from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = PROJECT_ROOT / "corpus" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "corpus" / "processed"
OUTPUT_FILE = PROCESSED_DIR / "chunks.json"

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


def extract_pages():
    """Extract text from PDFs while preserving page-level metadata."""
    documents = []

    for pdf_path in sorted(CORPUS_DIR.glob("*.pdf")):
        reader = PdfReader(str(pdf_path))

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()

            if not text:
                continue

            documents.append(
                {
                    "source": pdf_path.name,
                    "page": page_number,
                    "text": text,
                }
            )

    return documents


def create_chunks(pages):
    """Split page text into overlapping chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []

    for page in pages:
        page_chunks = splitter.split_text(page["text"])

        for index, text in enumerate(page_chunks):
            chunks.append(
                {
                    "chunk_id": f"{page['source']}:p{page['page']}:c{index}",
                    "source": page["source"],
                    "page": page["page"],
                    "text": text,
                }
            )

    return chunks


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    pages = extract_pages()
    chunks = create_chunks(pages)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(chunks, file, ensure_ascii=False, indent=2)

    print(f"PDF pages with extractable text: {len(pages)}")
    print(f"Chunks created: {len(chunks)}")
    print(f"Output: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()