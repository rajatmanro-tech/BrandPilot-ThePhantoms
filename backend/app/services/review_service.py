from google.genai.errors import ServerError
from openai import OpenAIError

from app.services.gemini_service import review_content
from app.services.groq_service import review_content_groq
from app.services.openai_service import review_content_openai


def review_content_with_fallback(content: str, brand_rules: list[dict]):
    # First provider: Gemini
    try:
        print("Attempting review with Gemini...", flush=True)

        result = review_content(content, brand_rules)

        print("Review completed using Gemini.", flush=True)
        return result, "gemini"

    except ServerError as error:
        if error.code not in (503, 504):
            raise

        print(f"Gemini unavailable (HTTP {error.code}).", flush=True)

    # Second provider: Groq
    try:
        print("Attempting review with Groq...", flush=True)

        result = review_content_groq(content, brand_rules)

        print("Review completed using Groq.", flush=True)
        return result, "groq"

    except (OpenAIError, ValueError) as error:
        print(f"Groq unavailable: {type(error).__name__}", flush=True)

    # Third provider: OpenAI
    try:
        print("Attempting review with OpenAI...", flush=True)

        result = review_content_openai(content, brand_rules)

        print("Review completed using OpenAI.", flush=True)
        return result, "openai"

    except (OpenAIError, ValueError) as error:
        print(f"OpenAI unavailable: {type(error).__name__}", flush=True)

        raise RuntimeError(
            "All AI review providers are currently unavailable. "
            "Please try again later."
        ) from error