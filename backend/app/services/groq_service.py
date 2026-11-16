
import json
import traceback

from openai import OpenAI

from app.core.config import settings
from app.services.gemini_service import GeminiReviewResult


client = OpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
    timeout=60.0,
    max_retries=1,
)


def extract_json(text: str) -> dict:
    """Extract a JSON object from the model response."""

    text = text.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        if lines[-1].strip().startswith("```"):
            text = "\n".join(lines[1:-1]).strip()

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in Groq response.")

    depth = 0
    in_string = False
    escaped = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

                if depth == 0:
                    return json.loads(text[start:index + 1])

    raise ValueError("Groq returned incomplete JSON.")


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

    schema = GeminiReviewResult.model_json_schema()

    prompt = f"""
You are a precise brand governance reviewer.

Review the submitted content against the supplied brand rules.

BRAND RULES:
{rules_text or "No specific brand rules provided."}

CONTENT:
<content>
{content}
</content>

REQUIRED JSON SCHEMA:
{json.dumps(schema, ensure_ascii=False)}

INSTRUCTIONS:
- Return exactly one JSON object.
- Follow the supplied schema exactly.
- Include every required field.
- Use correct field names and data types.
- Use only allowed enum values.
- Do not include Markdown or code fences.
- Report only genuine, identifiable issues.
- Do not invent violations.
- Every finding must be supported by an exact excerpt.
- Use exact text from submitted content for original_text.
- Only report issues connected to an applicable brand rule.
- Avoid duplicate findings.
- Keep explanations and suggestions concise.

REPLACEMENT TEXT RULES:
- suggestion must explain what should change.
- replacement_text must contain complete, ready-to-use corrected wording.
- replacement_text must be actual replacement copy, not instructions.
- Never copy suggestion into replacement_text.
- Preserve meaning wherever possible.
- Do not invent facts, statistics, evidence, or guarantees.
- If no safe replacement can be written without additional
  information, set replacement_text to null.
- If a neutral and safe rewrite is possible, provide it.

SCORING:
- Start with 100 points.
- Critical issue: deduct 25 points.
- High issue: deduct 15 points.
- Medium issue: deduct 8 points.
- Low issue: deduct 3 points.
- Do not deduct points for duplicate findings.
- Final score cannot be below 0.
- A score of 100 means fully compliant.

For every finding:
- Generate replacement_text whenever a safe rewrite is possible.
- For exaggerated performance claims, remove unsupported statistics.
- For absolute promises, use realistic qualified wording.
- For urgency-heavy language, provide neutral promotional wording.
- For conflicting offer dates, return null until dates are verified.
- For image alt text, use only available image context.
- Never invent facts, statistics, prices, or guarantees.
"""

    last_error = None

    for attempt in range(2):

        current_prompt = prompt

        if attempt == 1:
            current_prompt += f"""

RETRY INSTRUCTIONS:
Your previous response failed validation.
Return a complete JSON object matching the schema.
Correct the previous error.

Previous error:
{str(last_error)[:1000]}
"""

        print(
            f"Groq review attempt {attempt + 1}/2...",
            flush=True,
        )

        try:
            response = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a brand governance reviewer. "
                            "Return only one valid JSON object. "
                            "Follow the supplied schema exactly. "
                            "Provide real replacement wording, "
                            "never editing instructions as replacement text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": current_prompt,
                    },
                ],
                max_completion_tokens=4000,
                reasoning_effort="low",
            )

        except Exception as error:
            print(
                f"GROQ API REQUEST FAILED: {type(error).__name__}: {error}",
                flush=True,
            )
            traceback.print_exc()
            raise

        try:
            message = response.choices[0].message
            output = message.content

            if not output:
                raise ValueError(
                    f"Groq returned empty content. "
                    f"Finish reason: {response.choices[0].finish_reason}"
                )

            data = extract_json(output)
            result = GeminiReviewResult.model_validate(data)

            print("Groq review completed successfully.", flush=True)
            return result

        except Exception as error:
            last_error = error

            print(
                f"GROQ RESPONSE VALIDATION FAILED: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            traceback.print_exc()

    raise ValueError(
        f"Groq failed after two attempts. Last error: {last_error}"
    )
