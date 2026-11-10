
import json

from openai import OpenAI, OpenAIError, BadRequestError

from app.core.config import settings
from app.services.gemini_service import GeminiReviewResult


client = OpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    timeout=45.0,
    max_retries=1,
)


def make_groq_compatible(schema: dict) -> dict:
    """Convert Pydantic JSON Schema into Groq-compatible strict schema."""

    if isinstance(schema, dict):
        if schema.get("type") == "object":
            properties = schema.get("properties", {})
            schema["additionalProperties"] = False
            schema["required"] = list(properties.keys())

        for value in schema.values():
            if isinstance(value, dict):
                make_groq_compatible(value)

            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        make_groq_compatible(item)

    return schema


def review_content_groq(
    content: str,
    brand_rules: list[dict],
) -> GeminiReviewResult:

    rules_text = "\n".join(
        f"- Category: {rule['category']}\n"
        f"  Title: {rule['title']}\n"
        f"  Description: {rule['description']}\n"
        f"  Severity: {rule['severity']}"
        for rule in brand_rules
    )

    schema = make_groq_compatible(
        GeminiReviewResult.model_json_schema()
    )

    prompt = f"""
You are a precise and consistent brand governance reviewer.

Review the submitted content against the supplied brand rules.

BRAND RULES:
{rules_text or "No specific brand rules provided."}

CONTENT:
{content}

EVALUATE:
1. Tone and brand voice.
2. Terminology consistency.
3. Unsupported or misleading factual claims.
4. Messaging and brand consistency.
5. Accessibility.

STRICT INSTRUCTIONS:
- Report only genuine, identifiable issues.
- Do not invent violations.
- Every finding must be supported by an exact excerpt.
- Use exact text from the submitted content for original_text.
- Only report issues connected to an applicable brand rule.
- Do not report subjective preferences as violations.
- Avoid duplicate findings.
- Apply severity consistently.
- Keep explanations and suggestions concise.
- Return valid JSON matching the required schema.
- Do not include Markdown or additional fields.

SCORING RUBRIC:
- Start with 100 points.
- Critical issue: deduct 25 points.
- High issue: deduct 15 points.
- Medium issue: deduct 8 points.
- Low issue: deduct 3 points.
- Do not deduct points for duplicate findings.
- Final score cannot be below 0.
- Apply deductions consistently.
- A score of 100 means fully compliant.
"""

    for attempt in range(2):
        try:
            current_prompt = prompt

            if attempt == 1:
                current_prompt += """

RETRY INSTRUCTIONS:
Your previous response failed JSON validation.
Follow the required schema exactly.
Include every required field.
Use correct data types and allowed severity values.
Return only valid JSON.
"""

            print(
                f"Groq review attempt {attempt + 1}/2...",
                flush=True,
            )

            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise and consistent brand "
                            "governance reviewer. Return only valid "
                            "structured JSON matching the required schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": current_prompt,
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "brand_review",
                        "strict": True,
                        "schema": schema,
                    },
                },
                temperature=0,
                max_tokens=1800,
            )

            result = response.choices[0].message.content

            if not result:
                raise ValueError("Groq returned an empty response.")

            return GeminiReviewResult.model_validate_json(result)

        except BadRequestError as error:
            error_details = getattr(error, "body", {}) or {}
            error_code = error_details.get("code")

            print(
                f"Groq API error: {error_code} - {error}",
                flush=True,
            )

            if error_code == "json_validate_failed" and attempt == 0:
                print(
                    "Retrying Groq due to invalid JSON...",
                    flush=True,
                )
                continue

            raise

        except ValueError as error:
            print(
                f"Groq validation failed on attempt {attempt + 1}: {error}",
                flush=True,
            )

            if attempt == 1:
                raise

        except OpenAIError:
            raise

    raise RuntimeError("Groq review failed after retries.")
