import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing from .env")

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=api_key,
        temperature=0,
        timeout=30,
        max_retries=2,
    )

    response = llm.invoke(
        "Reply with exactly: Gemini connection successful."
    )

    print("Model:", model_name)
    print("Response:", response.content)


if __name__ == "__main__":
    main()