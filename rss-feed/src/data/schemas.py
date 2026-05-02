from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class WebsiteCreate(BaseModel):
    name: str
    url: str


class WebsiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    url: str
    domain: str
    created_at: datetime
    discovery_status: str


class FeedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    website_id: int
    feed_url: str
    title: str | None
    feed_type: str | None
    last_parsed_at: datetime | None


class ArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feed_id: int
    url: str
    title: str | None
    author: str | None
    published_at: datetime | None
    status: str


class ArticleDetailResponse(ArticleResponse):
    summary: str | None
    original_html: str | None
    extracted_text: str | None
    feedparser_raw_entry: dict | None


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class BatchSummaryResponse(BaseModel):
    feeds_parsed: int
    articles_discovered: int
    articles_extracted: int
    errors: list[str]


class DiscoveryResponse(BaseModel):
    website_id: int
    feeds_found: int
    feeds: list[FeedResponse]


class ParseResponse(BaseModel):
    feed_id: int | None
    articles_found: int
    new_articles: int


class ExtractBatchResponse(BaseModel):
    feed_id: int
    total: int
    extracted: int
    failed: int
    errors: list[str]


class ErrorResponse(BaseModel):
    error: str
    message: str
    request_id: str | None = None
    details: list[dict] | None = None


class StatusResponse(BaseModel):
    total_websites: int
    total_feeds: int
    total_articles: int
    articles_by_status: dict[str, int]
