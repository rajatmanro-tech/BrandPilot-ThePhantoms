from openai import OpenAI

from app.core.config import settings
from app.services.gemini_service import GeminiReviewResult


client = OpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    timeout=60.0,
    max_retries=2,
)
def make_groq_compatible(schema: dict) -> dict:
    for value in schema.values():
        if isinstance(value, dict):
            make_groq_compatible(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    make_groq_compatible(item)

    if schema.get("type") == "object":
        schema["additionalProperties"] = False

    return schema


def review_content_groq(content: str, brand_rules: list[dict]) -> GeminiReviewResult:
    rules_text = "\n".join(
        f"- Category: {rule['category']}\n"
        f"  Title: {rule['title']}\n"
        f"  Description: {rule['description']}\n"
        f"  Severity: {rule['severity']}"
        for rule in brand_rules
    )

    prompt = f"""
Review the following content against the brand rules.

BRAND RULES:
{rules_text or "No specific brand rules provided."}

CONTENT:
{content}

Evaluate tone, terminology, messaging, factual claims, and brand consistency.

Return:
- overall_status: pass, needs_changes, or fail
- overall_score: integer from 0 to 100
- summary: short explanation
- findings: list of issues, each with category, severity, issue,
  explanation, suggestion, and original_text.

Only report genuine issues. Do not invent violations.
"""

    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": "You are a precise brand governance reviewer.",
            },
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "brand_review",
                "strict": True,
                "schema": make_groq_compatible(
                    GeminiReviewResult.model_json_schema()
),
            },
        },
        temperature=0.2,
    )

    result = response.choices[0].message.content

    if not result:
        raise ValueError("Groq returned an empty response.")

    return GeminiReviewResult.model_validate_json(result)