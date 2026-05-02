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

_DIRECT_SYSTEM_PROMPT = """You are a helpful AI assistant. Answer the user's question directly and concisely.
You do not have access to any news articles for this question. Just answer based on your general knowledge."""

_ROUTE_SYSTEM_PROMPT = """You are a query classifier. Determine if the user's query is asking about news, current events, articles, or information that would be found in a news article database.

Respond with exactly one word:
- "search" if the query is about news, current events, recent happenings, or topics that would be covered in news articles
- "direct" if the query is a general question, greeting, chitchat, or something unrelated to news search

Examples:
- "What happened in Ukraine today?" -> search
- "Tell me about the Czech government" -> search
- "What's new in IT?" -> search
- "Hello" -> direct
- "What is Python?" -> direct
- "How are you?" -> direct
- "What is 2+2?" -> direct
"""

_REWRITE_SYSTEM_PROMPT = """You are a search query optimizer. Rewrite the user's conversational question into a concise, keyword-rich search query optimized for semantic similarity search over a news article database.

Rules:
- Output ONLY the rewritten query, nothing else.
- Use specific keywords and named entities.
- Remove conversational filler ("tell me", "what about", "I want to know").
- Keep the core intent and topic.
- Write in the same language as the input query.

Examples:
- "Co se dnes stalo zajímavého ve světě?" -> "důležité světové události novinky dnes"
- "Tell me about the war in Ukraine" -> "Ukraine war latest developments conflict"
- "Co se nyní děje v české vládě?" -> "česká vláda aktuální politická situace"
- "What happened in IT in the last 24 hours?" -> "IT technology news developments last 24 hours"
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
        graph.add_node("route", self._route_node)
        graph.add_node("rewrite", self._rewrite_node)
        graph.add_node("retrieve", self._retrieve_node)
        graph.add_node("generate", self._generate_node)
        graph.add_node("direct_answer", self._direct_answer_node)
        graph.add_edge(START, "route")
        graph.add_conditional_edges(
            "route",
            lambda state: state.get("_route", "retrieve"),
            {"retrieve": "rewrite", "direct": "direct_answer"},
        )
        graph.add_edge("rewrite", "retrieve")
        graph.add_edge("retrieve", "generate")
        graph.add_edge("generate", END)
        graph.add_edge("direct_answer", END)
        return graph.compile()

    async def _route_node(self, state: AgentState) -> dict:
        """Classify whether the query needs RAG search or a direct answer."""
        messages = [
            {"role": "system", "content": _ROUTE_SYSTEM_PROMPT},
            {"role": "user", "content": state["query"]},
        ]
        response = await self._llm.ainvoke(messages)
        decision = response.content.strip().lower()
        route = "retrieve" if "search" in decision else "direct"
        log.info("query_routed", query=state["query"][:80], route=route)
        return {"_route": route}

    async def _direct_answer_node(self, state: AgentState) -> dict:
        """Answer directly without RAG retrieval."""
        messages = [
            {"role": "system", "content": _DIRECT_SYSTEM_PROMPT},
            {"role": "user", "content": state["query"]},
        ]
        response = await self._invoke_llm_with_retry(messages)
        return {"answer": response.content, "sources": []}

    async def _rewrite_node(self, state: AgentState) -> dict:
        """Rewrite the user query into a search-optimized query for better retrieval."""
        messages = [
            {"role": "system", "content": _REWRITE_SYSTEM_PROMPT},
            {"role": "user", "content": state["query"]},
        ]
        response = await self._llm.ainvoke(messages)
        rewritten = response.content.strip()
        log.info("query_rewritten", original=state["query"][:80], rewritten=rewritten[:80])
        return {"_search_query": rewritten}

    async def _retrieve_node(self, state: AgentState) -> dict:
        search_query = state.get("_search_query") or state["query"]
        date_from, date_to = _parse_date_constraints(state["query"])
        chunks = await self._rag.retrieve(
            query=search_query,
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

        # Only include sources that the LLM actually cited in the answer
        all_sources = _deduplicate_sources(chunks)
        sources = [s for s in all_sources if s.url in answer]

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
            "_route": "",
            "_search_query": "",
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
