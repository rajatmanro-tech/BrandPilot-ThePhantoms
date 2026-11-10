
from unittest.mock import patch, MagicMock

from google.genai.errors import ServerError

from app.services.review_service import review_content_with_fallback


sample_rules = [
    {
        "category": "Tone of Voice",
        "title": "Professional Communication",
        "description": "Maintain a professional tone.",
        "severity": "high",
    }
]

sample_content = "Yo guys! This is our product."


# Scenario 1: Gemini succeeds
print("\nTEST 1: Gemini succeeds")

with patch(
    "app.services.review_service.review_content"
) as gemini, patch(
    "app.services.review_service.review_content_openai"
) as openai:

    expected = MagicMock()
    gemini.return_value = expected

    result = review_content_with_fallback(
        sample_content, sample_rules
    )

    assert result is expected
    openai.assert_not_called()

    print("PASSED: Gemini result returned.")


# Scenario 2: Gemini returns 503, OpenAI succeeds
print("\nTEST 2: Gemini unavailable, OpenAI succeeds")

with patch(
    "app.services.review_service.review_content"
) as gemini, patch(
    "app.services.review_service.review_content_openai"
) as openai:

    gemini.side_effect = ServerError(
        503, {"error": {"message": "Temporary overload"}}
    )

    expected = MagicMock()
    openai.return_value = expected

    result = review_content_with_fallback(
        sample_content, sample_rules
    )

    assert result is expected
    openai.assert_called_once()

    print("PASSED: OpenAI fallback returned.")


# Scenario 3: Gemini returns 504, OpenAI succeeds
print("\nTEST 3: Gemini timeout, OpenAI succeeds")

with patch(
    "app.services.review_service.review_content"
) as gemini, patch(
    "app.services.review_service.review_content_openai"
) as openai:

    gemini.side_effect = ServerError(
        504, {"error": {"message": "Deadline exceeded"}}
    )

    expected = MagicMock()
    openai.return_value = expected

    result = review_content_with_fallback(
        sample_content, sample_rules
    )

    assert result is expected
    openai.assert_called_once()

    print("PASSED: OpenAI fallback returned after timeout.")


print("\nALL FALLBACK TESTS PASSED")
