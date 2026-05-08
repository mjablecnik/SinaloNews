from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from src.schemas import TagResponse


# --- LLM Input Schemas ---


class ArticleForClustering(BaseModel):
    id: int
    title: str | None
    summary: str
    source_url: str | None


class ExistingGroupForClustering(BaseModel):
    group_id: int
    title: str
    summary: str


# --- LLM Structured Output Schemas ---


class ClusterItem(BaseModel):
    article_ids: list[int]
    topic: str
    justification: str


class ExistingGroupAddition(BaseModel):
    group_id: int
    article_ids: list[int]


class ClusteringLLMResponse(BaseModel):
    groups: list[ClusterItem]
    existing_group_additions: list[ExistingGroupAddition]
    standalone_ids: list[int]


class GroupDetailLLMResponse(BaseModel):
    title: str
    summary: str
    detail: str


# --- Pipeline Input Schemas ---


class ArticleForDetail(BaseModel):
    id: int
    title: str | None
    extracted_text: str | None


# --- Pipeline Output Data Classes ---


@dataclass
class ClusteringOutput:
    groups: list[ClusterItem] = field(default_factory=list)
    existing_group_additions: list[ExistingGroupAddition] = field(default_factory=list)
    standalone_ids: list[int] = field(default_factory=list)


@dataclass
class GroupDetailOutput:
    title: str
    summary: str
    detail: str


# --- API Response Schemas ---


class GroupMemberResponse(BaseModel):
    id: int
    title: str | None
    url: str | None
    author: str | None
    published_at: datetime | None
    summary: str | None
    importance_score: int


class GroupSummaryResponse(BaseModel):
    id: int
    title: str
    summary: str
    category: str
    grouped_date: date
    member_count: int
    importance_score: int
    tags: list[TagResponse] = []
    created_at: datetime


class GroupDetailResponse(BaseModel):
    id: int
    title: str
    summary: str
    detail: str
    category: str
    grouped_date: date
    member_count: int
    importance_score: int
    tags: list[TagResponse] = []
    created_at: datetime
    members: list[GroupMemberResponse]


class FeedItem(BaseModel):
    type: Literal["article", "group"]
    id: int
    title: str | None
    summary: str | None
    category: str
    importance_score: int
    tags: list[TagResponse] = []
    # Article-specific (None for groups)
    url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    content_type: str | None = None
    classified_at: datetime | None = None
    # Group-specific (None for articles)
    grouped_date: date | None = None
    member_count: int | None = None


class FeedResponse(BaseModel):
    items: list[FeedItem]
    total: int
    page: int
    size: int
    pages: int


class GroupingTriggerResponse(BaseModel):
    groups_created: int
    groups_updated: int
    articles_grouped: int
    date: date
