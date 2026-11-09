
from app.services.gemini_service import review_content

sample_rules = [
    {
        "category": "Tone of Voice",
        "title": "Professional Communication",
        "description": "All communication must maintain a professional and approachable tone.",
        "severity": "high",
    },
    {
        "category": "Terminology",
        "title": "Approved Product Name",
        "description": "Always use BrandPilot instead of BP or other abbreviations.",
        "severity": "medium",
    },
]

sample_content = """
Yo guys! BP is the coolest thing ever.
"""

print("Starting Gemini review...", flush=True)

try:
    result = review_content(sample_content, sample_rules)

    print("\n--- GEMINI REVIEW RESULT ---")
    print(result.model_dump_json(indent=2))

except Exception as error:
    print("\nGemini request failed:")
    print(type(error).__name__, str(error))
