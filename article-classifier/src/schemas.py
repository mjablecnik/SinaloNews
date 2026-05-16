from datetime import datetime

from pydantic import BaseModel


# --- LLM Structured Output ---


class TagOutput(BaseModel):
    category: str
    subcategory: str


class LLMClassificationResponse(BaseModel):
    tags: list[TagOutput]
    content_type: str
    score: int
    reason: str
    summary: str


# --- API Response Schemas ---


class TagResponse(BaseModel):
    category: str
    subcategory: str


class ClassifiedArticleResponse(BaseModel):
    id: int
    title: str | None
    url: str | None
    author: str | None
    published_at: datetime | None
    tags: list[TagResponse]
    content_type: str
    importance_score: int
    summary: str | None
    classified_at: datetime


class ArticleDetailResponse(ClassifiedArticleResponse):
    extracted_text: str | None
    formatted_text: str | None
    image_url: str | None


class PaginatedResponse(BaseModel):
    items: list[ClassifiedArticleResponse]
    total: int
    page: int
    size: int
    pages: int


class ClassifyTriggerResponse(BaseModel):
    queued: int
    message: str


class ClassifyStatusResponse(BaseModel):
    status: str  # "idle" or "processing"
    pending: int
    classified: int


class CategoryCountResponse(BaseModel):
    category: str
    count: int


class CategoriesResponse(BaseModel):
    categories: list[CategoryCountResponse]
    total: int


class HealthResponse(BaseModel):
    status: str
    database: str
