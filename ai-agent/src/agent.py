import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from src.rag import RAGPipeline
from src.schemas import AgentState, RetrievedChunk, SourceInfo

log = structlog.get_logger()


@dataclass
class AgentResponse:
    answer: str
    sources: list[SourceInfo]
    retrieved_chunk_count: int
    processing_time_ms: float


def configure_langsmith(settings) -> None:
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = settings.LANGSMITH_TRACING
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
    else:
        logging.getLogger(__name__).warning(
            "LANGSMITH_API_KEY is not set — tracing is disabled"
        )


def _parse_date_constraints(
    query: str,
) -> tuple[datetime | None, datetime | None]:
    """Extract date_from / date_to from natural-language time references."""
    now = datetime.now(timezone.utc)
    query_lower = query.lower()

    patterns = [
        (r"last\s+24\s+hours?", lambda: (now - timedelta(hours=24), now)),
        (r"today", lambda: (now.replace(hour=0, minute=0, second=0, microsecond=0), now)),
        (r"yesterday", lambda: (
            (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0),
            now.replace(hour=0, minute=0, second=0, microsecond=0),
        )),
        (r"this\s+week", lambda: (now - timedelta(days=now.weekday()), now)),
        (r"last\s+week", lambda: (
            now - timedelta(days=now.weekday() + 7),
            now - timedelta(days=now.weekday()),
        )),
        (r"last\s+(\d+)\s+days?", None),
        (r"past\s+(\d+)\s+days?", None),
    ]

    for pattern, factory in patterns:
        match = re.search(pattern, query_lower)
        if not match:
            continue
        if factory is not None:
            return factory()
        # numbered day patterns
        days = int(match.group(1))
        return (now - timedelta(days=days), now)

    return None, None


_SYSTEM_PROMPT = """You are an AI news assistant. Answer questions based ONLY on the provided article excerpts.

Rules:
- Only use information from the provided context. Do not use outside knowledge.
- Cite every piece of information with its source using the format [Title](URL).
- If no relevant articles were found, say so clearly.
- Keep answers concise and factual.
"""


def _build_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        pub = chunk.published_at.date().isoformat() if chunk.published_at else "unknown date"
        parts.append(
            f"[{i}] \"{chunk.article_title}\" ({pub})\n"
            f"URL: {chunk.article_url}\n"
            f"{chunk.chunk_text}"
        )
    return "\n\n---\n\n".join(parts)


def _deduplicate_sources(chunks: list[RetrievedChunk]) -> list[SourceInfo]:
    seen: set[str] = set()
    sources: list[SourceInfo] = []
    for chunk in chunks:
        if chunk.article_url not in seen:
            seen.add(chunk.article_url)
            sources.append(
                SourceInfo(
                    title=chunk.article_title,
                    url=chunk.article_url,
                    published_at=chunk.published_at,
                )
            )
    return sources


class NewsAgent:
    def __init__(self, rag_pipeline: RAGPipeline, settings) -> None:
        self._rag = rag_pipeline
        self._settings = settings
        self._llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/sinalo/ai-news-agent",
                "X-Title": "AI News Agent",
            },
        )
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("generate", self._generate_node)
        graph.add_edge(START, "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", END)
        return graph.compile()

    async def _retrieve_node(self, state: AgentState) -> dict:
        date_from, date_to = _parse_date_constraints(state["query"])
        chunks = await self._rag.retrieve(
            query=state["query"],
            date_from=date_from,
            date_to=date_to,
        )
        return {
            "retrieved_chunks": chunks,
            "date_from": date_from,
            "date_to": date_to,
        }

    async def _generate_node(self, state: AgentState) -> dict:
        chunks: list[RetrievedChunk] = state["retrieved_chunks"]

        if not chunks:
            return {
                "answer": (
                    "I couldn't find any relevant news articles for your query "
                    "in the indexed content. Please try a different question or "
                    "check back after more articles have been indexed."
                ),
                "sources": [],
            }

        context = _build_context(chunks)
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Context articles:\n\n{context}\n\n"
                    f"Question: {state['query']}"
                ),
            },
        ]

        response = await self._invoke_llm_with_retry(messages)
        answer = response.content

        sources = _deduplicate_sources(chunks)
        return {"answer": answer, "sources": sources}

    async def _invoke_llm_with_retry(self, messages: list[dict]):
        try:
            return await self._llm.ainvoke(messages)
        except Exception as exc:
            # Retry once on rate-limit errors (HTTP 429)
            if "429" in str(exc) or "rate_limit" in str(exc).lower():
                log.warning("llm_rate_limit_retry", error=str(exc))
                await asyncio.sleep(2)
                return await self._llm.ainvoke(messages)
            raise

    async def query(self, user_query: str) -> AgentResponse:
        start = time.monotonic()
        initial_state: AgentState = {
            "query": user_query,
            "date_from": None,
            "date_to": None,
            "retrieved_chunks": [],
            "answer": "",
            "sources": [],
        }

        final_state = await self._graph.ainvoke(initial_state)

        elapsed_ms = (time.monotonic() - start) * 1000
        chunks: list[RetrievedChunk] = final_state.get("retrieved_chunks", [])
        sources: list[SourceInfo] = final_state.get("sources", [])

        log.info(
            "agent_query_complete",
            query=user_query[:100],
            retrieved_chunks=len(chunks),
            model=self._settings.LLM_MODEL,
            processing_time_ms=round(elapsed_ms, 2),
        )

        return AgentResponse(
            answer=final_state.get("answer", ""),
            sources=sources,
            retrieved_chunk_count=len(chunks),
            processing_time_ms=elapsed_ms,
        )
