from google.genai.errors import ServerError
from openai import OpenAIError

from app.services.gemini_service import review_content
from app.services.groq_service import review_content_groq
from app.services.openai_service import review_content_openai


def review_content_with_fallback(content: str, brand_rules: list[dict]):
    # Primary provider: Groq
    try:
        print("Attempting review with Groq...", flush=True)

        result = review_content_groq(content, brand_rules)

        print("Review completed using Groq.", flush=True)
        return result, "groq"

    except OpenAIError as error:
        print(f"GROQ ERROR TYPE: {type(error).__name__}", flush=True)
        print(f"GROQ ERROR DETAILS: {getattr(error, 'body', None)}", flush=True)
        print(f"GROQ ERROR MESSAGE: {error}", flush=True)

        print("Groq unavailable. Trying Gemini...", flush=True)

    except ValueError as error:
        print(f"Groq returned invalid data: {error}", flush=True)

    # Fallback provider: Gemini
    try:
        print("Attempting review with Gemini...", flush=True)

        result = review_content(content, brand_rules)

        print("Review completed using Gemini.", flush=True)
        return result, "gemini"

    except (ServerError, ValueError) as error:
        print(
            f"Gemini unavailable: {type(error).__name__}: {error}",
            flush=True,
        )

    # Last fallback: OpenAI
    try:
        print("Attempting review with OpenAI...", flush=True)

        result = review_content_openai(content, brand_rules)

        print("Review completed using OpenAI.", flush=True)
        return result, "openai"

    except (OpenAIError, ValueError) as error:
        print(
            f"OpenAI unavailable: {type(error).__name__}: {error}",
            flush=True,
        )

        raise RuntimeError(
            "All AI review providers are currently unavailable. "
            "Please try again later."
        ) from error