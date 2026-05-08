import asyncio
from dataclasses import dataclass

import structlog
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from src.grouping_schemas import (
    ArticleForClustering,
    ArticleForDetail,
    ClusteringLLMResponse,
    ClusteringOutput,
    ExistingGroupForClustering,
    GroupDetailLLMResponse,
    GroupDetailOutput,
)

log = structlog.get_logger()


# --- State types for LangGraph ---


class _ClusteringState(TypedDict):
    articles: list[ArticleForClustering]
    existing_groups: list[ExistingGroupForClustering]
    result: ClusteringOutput | None


class _DetailState(TypedDict):
    member_articles: list[ArticleForDetail]
    result: GroupDetailOutput | None


# --- Prompt builders ---

_CLUSTERING_SYSTEM_PROMPT = (
    "You are an expert news analyst. Your task is to identify clusters of news articles "
    "that cover the exact same specific topic, event, or story from different sources. "
    "Group articles only when they report on the same concrete thing — the same incident, "
    "announcement, decision, or event. Do NOT group articles merely because they share "
    "a broad category or theme. Return your analysis as structured JSON."
)


def _build_clustering_prompt(
    articles: list[ArticleForClustering],
    existing_groups: list[ExistingGroupForClustering],
) -> str:
    sections = []

    if existing_groups:
        sections.append("## Existing Groups (already formed for this date and category)")
        for g in existing_groups:
            sections.append(
                f"- Group ID {g.group_id}: {g.title}\n  Summary: {g.summary}"
            )
        sections.append("")

    sections.append("## Articles to Analyze")
    for a in articles:
        title = a.title or "(no title)"
        url = a.source_url or "(unknown source)"
        sections.append(f"### Article ID {a.id}")
        sections.append(f"Title: {title}")
        sections.append(f"Source: {url}")
        sections.append(f"Summary: {a.summary}")
        sections.append("")

    instructions = [
        "## Instructions",
        "Analyze the articles above and return a JSON object with:",
        "- `groups`: list of NEW groups to create. Each group must have at least 2 articles. "
        "Include `article_ids`, a brief `topic` description, and `justification`.",
        "- `existing_group_additions`: list of additions to EXISTING groups. "
        "Only include if new articles clearly belong to an existing group (by group_id). "
        "Include the `group_id` and `article_ids` to add.",
        "- `standalone_ids`: list of article IDs that do not clearly match any other article "
        "or existing group topic.",
        "",
        "Rules:",
        "- Each article ID must appear in exactly ONE of: groups, existing_group_additions, or standalone_ids.",
        "- A group requires at least 2 articles — never create a single-article group.",
        "- Only group articles covering the SAME SPECIFIC event/incident/announcement, "
        "not just the same broad topic.",
    ]
    sections.extend(instructions)

    return "\n".join(sections)


_DETAIL_SYSTEM_PROMPT = (
    "You are a professional Czech journalist. Your task is to write a consolidated news article "
    "in Czech that synthesizes information from multiple source articles covering the same topic. "
    "The output must be entirely in Czech, regardless of the source article language."
)


def _build_detail_prompt(member_articles: list[ArticleForDetail]) -> str:
    sections = ["## Source Articles"]

    for a in member_articles:
        title = a.title or "(no title)"
        text = a.extracted_text or "(no text available)"
        sections.append(f"### Article ID {a.id}: {title}")
        sections.append(text[:6000])  # Limit per article to avoid token overflow
        sections.append("")

    instructions = [
        "## Instructions",
        "Based on the source articles above, produce a JSON object with:",
        "- `title`: A concise title in Czech describing the shared topic (max 100 characters).",
        "- `summary`: A short one-paragraph summary in Czech (2-4 sentences) suitable for "
        "a card preview in a news reader. Do NOT include Markdown formatting.",
        "- `detail`: A longer combined article in Czech Markdown (approximately 2-5 paragraphs) "
        "that synthesizes all key facts, perspectives, and conclusions from the source articles. "
        "Include differing perspectives when present. Only include information from the sources — "
        "do not fabricate any facts.",
        "",
        "All output (title, summary, detail) MUST be written in Czech.",
    ]
    sections.extend(instructions)

    return "\n".join(sections)


class GroupingPipeline:
    def __init__(self, settings) -> None:
        self._settings = settings
        model = settings.GROUPING_LLM_MODEL or settings.LLM_MODEL
        self._llm = ChatOpenAI(
            model=model,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/sinalo/article-classifier",
                "X-Title": "Article Classifier",
            },
        )
        self._clustering_llm = self._llm.with_structured_output(
            ClusteringLLMResponse, include_raw=True
        )
        self._detail_llm = self._llm.with_structured_output(
            GroupDetailLLMResponse, include_raw=True
        )
        self._clustering_graph = self._build_clustering_graph()
        self._detail_graph = self._build_detail_graph()

    def _build_clustering_graph(self):
        graph = StateGraph(_ClusteringState)
        graph.add_node("cluster", self._cluster_node)
        graph.add_edge(START, "cluster")
        graph.add_edge("cluster", END)
        return graph.compile()

    def _build_detail_graph(self):
        graph = StateGraph(_DetailState)
        graph.add_node("generate", self._detail_node)
        graph.add_edge(START, "generate")
        graph.add_edge("generate", END)
        return graph.compile()

    async def _call_with_retry(self, structured_llm, messages: list[dict]) -> dict:
        for attempt in range(self._settings.LLM_MAX_RETRIES + 1):
            try:
                return await structured_llm.ainvoke(messages)
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
                    "grouping_llm_retry",
                    attempt=attempt + 1,
                    max_retries=self._settings.LLM_MAX_RETRIES,
                    delay=self._settings.LLM_RETRY_DELAY_SECONDS,
                    error=exc_str[:200],
                )
                await asyncio.sleep(self._settings.LLM_RETRY_DELAY_SECONDS)
        raise RuntimeError("Unreachable")  # pragma: no cover

    async def _cluster_node(self, state: _ClusteringState) -> dict:
        user_prompt = _build_clustering_prompt(state["articles"], state["existing_groups"])
        messages = [
            {"role": "system", "content": _CLUSTERING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = await self._call_with_retry(self._clustering_llm, messages)
        parsed: ClusteringLLMResponse = raw_result["parsed"]

        result = ClusteringOutput(
            groups=parsed.groups,
            existing_group_additions=parsed.existing_group_additions,
            standalone_ids=parsed.standalone_ids,
        )

        log.info(
            "clustering_complete",
            new_groups=len(parsed.groups),
            existing_additions=len(parsed.existing_group_additions),
            standalone=len(parsed.standalone_ids),
        )

        return {"result": result}

    async def _detail_node(self, state: _DetailState) -> dict:
        user_prompt = _build_detail_prompt(state["member_articles"])
        messages = [
            {"role": "system", "content": _DETAIL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        raw_result = await self._call_with_retry(self._detail_llm, messages)
        parsed: GroupDetailLLMResponse = raw_result["parsed"]

        result = GroupDetailOutput(
            title=parsed.title,
            summary=parsed.summary,
            detail=parsed.detail,
        )

        log.info("detail_generation_complete", title=parsed.title[:60] if parsed.title else "")

        return {"result": result}

    async def cluster(
        self,
        articles: list[ArticleForClustering],
        existing_groups: list[ExistingGroupForClustering],
    ) -> ClusteringOutput:
        """Single LLM call per category. Returns clusters + standalone IDs."""
        initial_state: _ClusteringState = {
            "articles": articles,
            "existing_groups": existing_groups,
            "result": None,
        }
        final_state = await self._clustering_graph.ainvoke(initial_state)
        result: ClusteringOutput | None = final_state["result"]
        if result is None:
            raise RuntimeError("Clustering pipeline returned no result")
        return result

    async def generate_detail(
        self,
        member_articles: list[ArticleForDetail],
    ) -> GroupDetailOutput:
        """Single LLM call per group. Returns title, summary, detail in Czech."""
        initial_state: _DetailState = {
            "member_articles": member_articles,
            "result": None,
        }
        final_state = await self._detail_graph.ainvoke(initial_state)
        result: GroupDetailOutput | None = final_state["result"]
        if result is None:
            raise RuntimeError("Detail generation pipeline returned no result")
        return result
