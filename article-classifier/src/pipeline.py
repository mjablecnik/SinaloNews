import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.constants import TAG_TAXONOMY, clamp_score, validate_content_type
from src.schemas import LLMClassificationResponse, TagOutput

log = structlog.get_logger()


@dataclass
class ClassificationOutput:
    tags: list[TagOutput]
    content_type: str
    importance_score: int
    summary: str
    reason: str
    llm_model: str
    token_usage: int | None
    processing_time_ms: float


class _PipelineState(TypedDict):
    article_title: str
    article_text: str
    article_summary: str | None
    existing_tags: list[dict]
    result: ClassificationOutput | None


_SYSTEM_PROMPT = (
    "You are an article classifier for a Czech news aggregator. "
    "Analyze the provided article and return a structured JSON classification "
    "with tags, content_type, score, reason, and summary. "
    "Use the provided current date and time to correctly infer any ambiguous or missing dates "
    "(e.g. missing year, relative references like 'yesterday' or 'next Monday')."
)

_CONTENT_TYPES_DOC = """Available content types:
- CONSPIRACY_THEORY: Content promoting unfounded conspiracy theories or misinformation
- CLICKBAIT: Sensationalized content with misleading headlines designed to generate clicks
- NO_USEFUL_CONTENT: Content with no informational value (ads, spam, broken content, satire)
- DIGEST: Daily news roundups, summaries of multiple unrelated events, "top stories of the day" compilations
- OPINION_EDITORIAL: Subjective opinion pieces, commentaries, columns, or reviews representing the author's personal viewpoint
- BREAKING_NEWS: Hard news with immediate impact (war, natural disasters, government collapse, major security events)
- GENERAL_VALUABLE_CONTENT: Informative content of general interest
- UNIVERSAL_RELEVANT_CONTENT: High-quality content of broad relevance and importance"""

_SCORING_CRITERIA = """Importance score criteria (for a Czech reader, 0–10):
- 9–10: Directly affects Czech Republic or Czech citizens (legislation changes, major domestic events)
- 7–8: European/global events with direct Czech consequences (EU regulations, trade agreements, security threats)
- 5–6: Significant global events of general importance without direct Czech impact
- 3–4: Notable events with limited personal relevance (foreign political scandals, distant regional conflicts)
- 1–2: Minor events with minimal informational value
- 0: Content with no informational value whatsoever

Increase the score for articles that could affect voting preferences or personal financial decisions.
Decrease the score for accidents or incidents abroad that do not directly affect Czech citizens."""

_INSTRUCTIONS = """Classification rules:
- Assign 1–5 tags from the tag taxonomy; prefer existing tags over creating new subcategories
- Main categories are fixed; you may propose new subcategories only when no existing one fits
- Write the summary in Czech language, approximately one paragraph in Markdown format
- The summary MUST capture ALL key facts, conclusions, names, numbers, dates, and actionable information
- Markdown formatting (bold, italic, bullet points) is allowed when it improves readability
- The summary MUST NOT contain any image URLs, base64 data, emoji sequences, or encoded strings
- The summary MUST NOT exceed 1000 characters
- The summary MUST contain only readable text — no raw URLs unless they are meaningful hyperlinks
- Write the reason field in English explaining why the given score and content type were assigned"""


def _format_tags(existing_tags: list[dict]) -> str:
    if existing_tags:
        by_category: dict[str, list[str]] = {}
        for tag in existing_tags:
            by_category.setdefault(tag["category"], []).append(tag["subcategory"])
    else:
        by_category = TAG_TAXONOMY  # type: ignore[assignment]

    lines = ["Tag taxonomy (prefer existing tags):"]
    for cat, subs in by_category.items():
        lines.append(f"  {cat}: {', '.join(subs)}")
    return "\n".join(lines)


def _build_user_prompt(
    article_title: str,
    article_text: str,
    article_summary: str | None,
    existing_tags: list[dict],
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sections = [
        f"Current date and time: {now}",
        f"Title: {article_title}",
        f"Article text:\n{article_text}",
    ]
    if article_summary:
        sections.append(f"Article summary:\n{article_summary}")
    sections += [
        _CONTENT_TYPES_DOC,
        _SCORING_CRITERIA,
        _format_tags(existing_tags),
        _INSTRUCTIONS,
    ]
    return "\n\n".join(sections)


class ClassificationPipeline:
    def __init__(self, settings) -> None:
        self._settings = settings
        self._llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/sinalo/article-classifier",
                "X-Title": "Article Classifier",
            },
        )
        self._structured_llm = self._llm.with_structured_output(
            LLMClassificationResponse, include_raw=True
        )
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(_PipelineState)
        graph.add_node("classify", self._classify_node)
        graph.add_edge(START, "classify")
        graph.add_edge("classify", END)
        return graph.compile()

    async def _classify_node(self, state: _PipelineState) -> dict:
        user_prompt = _build_user_prompt(
            state["article_title"],
            state["article_text"],
            state["article_summary"],
            state["existing_tags"],
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        start = time.monotonic()
        raw_result = await self._call_with_retry(messages)
        elapsed_ms = (time.monotonic() - start) * 1000

        parsed: LLMClassificationResponse = raw_result["parsed"]
        raw_message = raw_result.get("raw")

        token_usage: int | None = None
        if raw_message and hasattr(raw_message, "usage_metadata") and raw_message.usage_metadata:
            token_usage = raw_message.usage_metadata.get("total_tokens")

        content_type = validate_content_type(parsed.content_type)
        importance_score = clamp_score(parsed.score)

        if content_type != parsed.content_type:
            log.warning("invalid_content_type_fallback", received=parsed.content_type)
        if importance_score != parsed.score:
            log.warning("score_clamped", received=parsed.score, clamped=importance_score)

        result = ClassificationOutput(
            tags=parsed.tags,
            content_type=content_type,
            importance_score=importance_score,
            summary=parsed.summary,
            reason=parsed.reason,
            llm_model=self._settings.LLM_MODEL,
            token_usage=token_usage,
            processing_time_ms=elapsed_ms,
        )

        log.info(
            "article_classified",
            content_type=content_type,
            importance_score=importance_score,
            tags_count=len(parsed.tags),
            token_usage=token_usage,
            processing_time_ms=round(elapsed_ms, 2),
        )

        return {"result": result}

    async def _call_with_retry(self, messages: list[dict]) -> dict:
        for attempt in range(self._settings.LLM_MAX_RETRIES + 1):
            try:
                return await self._structured_llm.ainvoke(messages)
            except Exception as exc:
                exc_str = str(exc)
                is_retryable = (
                    "429" in exc_str
                    or "rate_limit" in exc_str.lower()
                    or "timeout" in exc_str.lower()
                )
                if not is_retryable or attempt >= self._settings.LLM_MAX_RETRIES:
                    raise
                log.warning(
                    "llm_retry",
                    attempt=attempt + 1,
                    max_retries=self._settings.LLM_MAX_RETRIES,
                    delay=self._settings.LLM_RETRY_DELAY_SECONDS,
                    error=exc_str[:200],
                )
                await asyncio.sleep(self._settings.LLM_RETRY_DELAY_SECONDS)
        raise RuntimeError("Unreachable")  # pragma: no cover

    async def classify(
        self,
        article_title: str,
        article_text: str,
        article_summary: str | None,
        existing_tags: list[dict],
    ) -> ClassificationOutput:
        """Run single LLM call, return validated structured output."""
        if len(article_text) < 100:
            return ClassificationOutput(
                tags=[],
                content_type="GENERAL_VALUABLE_CONTENT",
                importance_score=0,
                summary=article_text,
                reason="Short text bypass — extracted text under 100 characters.",
                llm_model=self._settings.LLM_MODEL,
                token_usage=None,
                processing_time_ms=0.0,
            )

        initial_state: _PipelineState = {
            "article_title": article_title,
            "article_text": article_text,
            "article_summary": article_summary,
            "existing_tags": existing_tags,
            "result": None,
        }

        final_state = await self._graph.ainvoke(initial_state)
        result: ClassificationOutput | None = final_state["result"]
        if result is None:
            raise RuntimeError("Classification pipeline returned no result")
        return result
