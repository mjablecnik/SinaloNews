from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# --- Requests ---

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


class IndexRequest(BaseModel):
    full_sync: bool = False


# --- Shared ---

class SourceInfo(BaseModel):
    title: str
    url: str
    published_at: datetime | None


class RetrievedChunk(BaseModel):
    chunk_text: str
    article_id: int
    article_title: str
    article_url: str
    published_at: datetime | None
    score: float


# --- Responses ---

class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    query: str
    processing_time_ms: float


class IndexingResult(BaseModel):
    articles_processed: int
    chunks_created: int
    errors: list[str]


class StatsResponse(BaseModel):
    total_articles_indexed: int
    total_chunks: int
    last_indexed_at: datetime | None


class HealthResponse(BaseModel):
    status: str
    database: str
    qdrant: str


class ErrorResponse(BaseModel):
    error: str
    message: str
    timestamp: datetime


# --- LangGraph Agent State ---

class AgentState(TypedDict):
    query: str
    date_from: datetime | None
    date_to: datetime | None
    retrieved_chunks: list[Any]  # list[RetrievedChunk] — kept as Any to avoid TypedDict nesting issues
    answer: str
    sources: list[Any]  # list[SourceInfo]
    _route: str  # "retrieve" or "direct"
