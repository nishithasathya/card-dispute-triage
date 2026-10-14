from pathlib import Path
from pypdf import PdfReader

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus" / "raw"


def inspect_pdf(pdf_path: Path) -> None:
    print(f"\n{'=' * 70}")
    print(f"FILE: {pdf_path.name}")
    print(f"{'=' * 70}")

    try:
        reader = PdfReader(str(pdf_path))

        print(f"Number of pages: {len(reader.pages)}")

        extracted_pages = 0

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""

            if text.strip():
                extracted_pages += 1

            if page_number <= 2:
                print(f"\n--- Page {page_number} ---")
                print(text[:1500] if text.strip() else "[No extractable text]")

        print(f"\nPages containing extractable text: {extracted_pages}")

        if extracted_pages == 0:
            print("WARNING: This PDF may require OCR.")

    except Exception as error:
        print(f"ERROR reading PDF: {error}")


def main() -> None:
    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))

    if not pdf_files:
        print(f"No PDF files found in: {CORPUS_DIR}")
        return

    for pdf_path in pdf_files:
        inspect_pdf(pdf_path)


if __name__ == "__main__":
    main()