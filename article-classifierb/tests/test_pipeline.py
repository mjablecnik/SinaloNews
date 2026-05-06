"""Property tests for classification pipeline validation logic.

Feature: article-classifier
"""

import asyncio

from hypothesis import given
from hypothesis import strategies as st

from src.constants import ContentType, clamp_score, validate_content_type
from src.pipeline import ClassificationPipeline


class _MockSettings:
    LLM_MODEL = "openai/gpt-4o-mini"
    OPENROUTER_API_KEY = "test-api-key"
    LLM_MAX_RETRIES = 3
    LLM_RETRY_DELAY_SECONDS = 5


_pipeline = ClassificationPipeline(_MockSettings())

_valid_content_types = {ct.value for ct in ContentType}


# Feature: article-classifier, Property 3: Content type validation with fallback
@given(st.text())
def test_content_type_validation_fallback(value: str):
    """For any string, validate_content_type returns the value if it matches ContentType,
    or GENERAL_VALUABLE_CONTENT otherwise."""
    result = validate_content_type(value)
    if value in _valid_content_types:
        assert result == value
    else:
        assert result == ContentType.GENERAL_VALUABLE_CONTENT.value


# Feature: article-classifier, Property 4: Score clamping
@given(st.integers())
def test_score_clamping(value: int):
    """For any integer, clamp_score returns max(0, min(10, value))."""
    result = clamp_score(value)
    assert result == max(0, min(10, value))
    assert 0 <= result <= 10


# Feature: article-classifier, Property 5: Short text bypass
@given(st.text(max_size=99))
def test_short_text_bypass(text: str):
    """For any article with extracted_text < 100 chars, the text is used as summary without LLM."""

    async def _run():
        result = await _pipeline.classify("Test Title", text, None, [])
        assert result.summary == text

    asyncio.run(_run())
