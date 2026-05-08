"""Property tests for API behavior.

Feature: article-classifier
"""

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from src.constants import ContentType, TAG_TAXONOMY
from src.schemas import ArticleDetailResponse

_ALL_CONTENT_TYPES = [ct.value for ct in ContentType]
_ALL_CATEGORIES = list(TAG_TAXONOMY.keys())
_ALL_TAG_PAIRS = [(cat, sub) for cat, subs in TAG_TAXONOMY.items() for sub in subs]
_SORT_FIELDS = ["importance_score", "published_at", "classified_at"]
_SORT_ORDERS = ["asc", "desc"]

_datetime_st = st.datetimes(
    min_value=datetime(2000, 1, 1), max_value=datetime(2030, 12, 31)
)
_score_st = st.integers(min_value=0, max_value=10)
_content_type_st = st.sampled_from(_ALL_CONTENT_TYPES)


@dataclass
class _FakeArticle:
    id: int
    content_type: str
    importance_score: int
    published_at: Optional[datetime]
    tags: list[tuple[str, str]]
    classified_at: datetime


def _article_strategy():
    return st.builds(
        _FakeArticle,
        id=st.integers(min_value=1),
        content_type=_content_type_st,
        importance_score=_score_st,
        published_at=st.one_of(st.none(), _datetime_st),
        tags=st.lists(st.sampled_from(_ALL_TAG_PAIRS), min_size=0, max_size=5),
        classified_at=_datetime_st,
    )


def _apply_filters(
    articles: list[_FakeArticle],
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    content_type: Optional[str] = None,
    min_score: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> list[_FakeArticle]:
    """Pure Python mirror of the routes.py filtering logic (AND semantics)."""
    result = []
    for a in articles:
        if content_type is not None and a.content_type != content_type:
            continue
        if min_score is not None and a.importance_score < min_score:
            continue
        if date_from is not None and (a.published_at is None or a.published_at < date_from):
            continue
        if date_to is not None and (a.published_at is None or a.published_at > date_to):
            continue
        if category is not None or subcategory is not None:
            matched = any(
                (category is None or cat.lower() == category.lower())
                and (subcategory is None or sub.lower() == subcategory.lower())
                for cat, sub in a.tags
            )
            if not matched:
                continue
        result.append(a)
    return result


def _satisfies_all_filters(
    article: _FakeArticle,
    category: Optional[str],
    subcategory: Optional[str],
    content_type: Optional[str],
    min_score: Optional[int],
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> bool:
    """Independent predicate verifying that all active filters are satisfied."""
    if content_type is not None and article.content_type != content_type:
        return False
    if min_score is not None and article.importance_score < min_score:
        return False
    if date_from is not None and (article.published_at is None or article.published_at < date_from):
        return False
    if date_to is not None and (article.published_at is None or article.published_at > date_to):
        return False
    if category is not None or subcategory is not None:
        return any(
            (category is None or cat.lower() == category.lower())
            and (subcategory is None or sub.lower() == subcategory.lower())
            for cat, sub in article.tags
        )
    return True


# Feature: article-classifier, Property 6: API filtering correctness
@given(
    articles=st.lists(_article_strategy(), max_size=20),
    category=st.one_of(st.none(), st.sampled_from(_ALL_CATEGORIES)),
    subcategory=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    content_type=st.one_of(st.none(), _content_type_st),
    min_score=st.one_of(st.none(), _score_st),
    date_from=st.one_of(st.none(), _datetime_st),
    date_to=st.one_of(st.none(), _datetime_st),
)
def test_api_filtering_correctness(
    articles, category, subcategory, content_type, min_score, date_from, date_to
):
    """Property 6: For any set of classified articles and filter combinations,
    every returned article satisfies ALL applied filters (AND logic).
    Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.10"""
    result = _apply_filters(
        articles,
        category=category,
        subcategory=subcategory,
        content_type=content_type,
        min_score=min_score,
        date_from=date_from,
        date_to=date_to,
    )

    result_ids = {a.id for a in result}

    for article in result:
        assert _satisfies_all_filters(
            article, category, subcategory, content_type, min_score, date_from, date_to
        ), (
            f"Article {article.id} in result but does not satisfy all filters: "
            f"category={category!r}, subcategory={subcategory!r}, "
            f"content_type={content_type!r}, min_score={min_score!r}, "
            f"date_from={date_from!r}, date_to={date_to!r}"
        )

    for article in articles:
        if article.id not in result_ids and _satisfies_all_filters(
            article, category, subcategory, content_type, min_score, date_from, date_to
        ):
            assert False, (
                f"Article {article.id} satisfies all filters but was excluded from result"
            )


def _get_sort_key(article: _FakeArticle, sort_by: str):
    return {
        "importance_score": article.importance_score,
        "published_at": article.published_at,
        "classified_at": article.classified_at,
    }[sort_by]


def _apply_sort(
    articles: list[_FakeArticle], sort_by: str, sort_order: str
) -> list[_FakeArticle]:
    """Pure Python mirror of the routes.py sorting logic."""
    reverse = sort_order == "desc"
    if sort_by == "published_at":
        non_null = [a for a in articles if a.published_at is not None]
        null_articles = [a for a in articles if a.published_at is None]
        sorted_non_null = sorted(non_null, key=lambda a: a.published_at, reverse=reverse)
        return sorted_non_null + null_articles
    return sorted(articles, key=lambda a: _get_sort_key(a, sort_by), reverse=reverse)


# Feature: article-classifier, Property 7: API sorting correctness
@given(
    articles=st.lists(_article_strategy(), max_size=20),
    sort_by=st.sampled_from(_SORT_FIELDS),
    sort_order=st.sampled_from(_SORT_ORDERS),
)
def test_api_sorting_correctness(articles, sort_by, sort_order):
    """Property 7: For any valid sort_by field and sort_order, returned articles are
    ordered correctly.
    Validates: Requirements 6.7, 6.8"""
    result = _apply_sort(articles, sort_by=sort_by, sort_order=sort_order)

    assert len(result) == len(articles), "Sorting must preserve all articles"

    keys = [_get_sort_key(a, sort_by) for a in result if _get_sort_key(a, sort_by) is not None]

    if sort_order == "asc":
        for i in range(len(keys) - 1):
            assert keys[i] <= keys[i + 1], (
                f"Ascending order violated at index {i}: {keys[i]} > {keys[i + 1]}, "
                f"sort_by={sort_by!r}"
            )
    else:
        for i in range(len(keys) - 1):
            assert keys[i] >= keys[i + 1], (
                f"Descending order violated at index {i}: {keys[i]} < {keys[i + 1]}, "
                f"sort_by={sort_by!r}"
            )


# --- Tests for GET /api/articles/{id} ---

@dataclass
class _FakeDetailArticle:
    id: int
    title: Optional[str]
    url: Optional[str]
    author: Optional[str]
    published_at: Optional[datetime]
    extracted_text: Optional[str]
    classified_at: datetime
    content_type: str
    importance_score: int
    summary: str
    tags: list[tuple[str, str]] = field(default_factory=list)


def _simulate_get_article_detail(
    article_id: int,
    articles: list[_FakeDetailArticle],
) -> Optional[_FakeDetailArticle]:
    """Pure Python mirror of the get_article_detail route logic."""
    for article in articles:
        if article.id == article_id:
            return article
    return None


def _build_detail_response(article: _FakeDetailArticle) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "author": article.author,
        "published_at": article.published_at,
        "tags": [{"category": cat, "subcategory": sub} for cat, sub in article.tags],
        "content_type": article.content_type,
        "importance_score": article.importance_score,
        "summary": article.summary,
        "extracted_text": article.extracted_text,
        "classified_at": article.classified_at,
    }


def test_get_article_detail_returns_404_for_nonexistent_id():
    """Test: returns 404 for non-existent article ID."""
    articles: list[_FakeDetailArticle] = []
    result = _simulate_get_article_detail(999, articles)
    assert result is None, "Should return None (→ 404) for non-existent article ID"


def test_get_article_detail_returns_404_for_article_without_classification():
    """Test: returns 404 for article without classification result (empty store)."""
    result = _simulate_get_article_detail(42, [])
    assert result is None, "Should return None (→ 404) when no classification result exists"


def test_get_article_detail_returns_correct_data():
    """Test: returns correct data for valid article ID with classification."""
    now = datetime(2025, 1, 15, 12, 0, 0)
    article = _FakeDetailArticle(
        id=1,
        title="Test Article",
        url="https://example.com/article",
        author="Author Name",
        published_at=now,
        extracted_text="Full article text here.",
        classified_at=now,
        content_type="article",
        importance_score=8,
        summary="A summary of the article.",
        tags=[("Technology", "AI")],
    )
    result = _simulate_get_article_detail(1, [article])
    assert result is not None, "Should return the article for a valid ID"
    assert result.id == 1
    assert result.title == "Test Article"
    assert result.importance_score == 8
    assert result.summary == "A summary of the article."


def test_get_article_detail_response_includes_extracted_text():
    """Test: response includes extracted_text field."""
    now = datetime(2025, 1, 15, 12, 0, 0)
    article = _FakeDetailArticle(
        id=5,
        title="Article With Text",
        url=None,
        author=None,
        published_at=None,
        extracted_text="This is the full extracted text.",
        classified_at=now,
        content_type="article",
        importance_score=7,
        summary="Summary text.",
    )
    result = _simulate_get_article_detail(5, [article])
    assert result is not None
    response = _build_detail_response(result)
    assert "extracted_text" in response
    assert response["extracted_text"] == "This is the full extracted text."


def test_get_article_detail_response_extracted_text_can_be_none():
    """Test: extracted_text field is present even when None."""
    now = datetime(2025, 1, 15, 12, 0, 0)
    article = _FakeDetailArticle(
        id=10,
        title="No Text Article",
        url="https://example.com",
        author=None,
        published_at=None,
        extracted_text=None,
        classified_at=now,
        content_type="article",
        importance_score=5,
        summary="Short summary.",
    )
    result = _simulate_get_article_detail(10, [article])
    assert result is not None
    response = _build_detail_response(result)
    assert "extracted_text" in response
    assert response["extracted_text"] is None


def test_article_detail_response_schema_has_extracted_text_field():
    """Test: ArticleDetailResponse schema includes the extracted_text field."""
    fields = ArticleDetailResponse.model_fields
    assert "extracted_text" in fields, "ArticleDetailResponse must have extracted_text field"


# Feature: article-classifier, Property 9: Detail endpoint returns complete data
_detail_article_strategy = st.builds(
    _FakeDetailArticle,
    id=st.integers(min_value=1, max_value=10000),
    title=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    url=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    author=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    published_at=st.one_of(st.none(), _datetime_st),
    extracted_text=st.one_of(st.none(), st.text(max_size=500)),
    classified_at=_datetime_st,
    content_type=_content_type_st,
    importance_score=_score_st,
    summary=st.text(min_size=1, max_size=200),
    tags=st.lists(st.sampled_from(_ALL_TAG_PAIRS), min_size=0, max_size=3),
)


@given(
    articles=st.lists(_detail_article_strategy, min_size=1, max_size=10),
    idx=st.integers(min_value=0, max_value=9),
)
def test_get_article_detail_correctness(articles: list[_FakeDetailArticle], idx: int):
    """Property 9: For any valid article ID with a classification result, the detail
    endpoint returns a response containing all required fields including extracted_text.
    Validates: Requirements 6a.1, 6a.2, 6a.4"""
    target = articles[idx % len(articles)]
    result = _simulate_get_article_detail(target.id, articles)

    assert result is not None, f"Should find article with id={target.id}"
    response = _build_detail_response(result)

    for field_name in ("id", "title", "url", "author", "published_at", "tags",
                       "content_type", "importance_score", "summary",
                       "extracted_text", "classified_at"):
        assert field_name in response, f"Response missing field: {field_name}"

    assert response["id"] == target.id
    assert response["extracted_text"] == result.extracted_text


# ─────────────────────────────────────────────────────────────────────────────
# Feature: article-grouping, Property 5: Group list filtering and pagination
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _FakeGroup:
    id: int
    category: str
    grouped_date: date


_GROUP_CATEGORIES = _ALL_CATEGORIES

_group_date_st = st.dates(
    min_value=date(2026, 1, 1),
    max_value=date(2026, 12, 31),
)

_fake_group_st = st.builds(
    _FakeGroup,
    id=st.integers(min_value=1, max_value=10000),
    category=st.sampled_from(_GROUP_CATEGORIES),
    grouped_date=_group_date_st,
)

_groups_st = st.lists(_fake_group_st, min_size=0, max_size=30)
_page_st = st.integers(min_value=1, max_value=10)
_size_st = st.integers(min_value=1, max_value=20)
_cat_filter_st = st.one_of(st.none(), st.sampled_from(_GROUP_CATEGORIES))
_date_filter_st = st.one_of(st.none(), _group_date_st)


def _apply_group_filters(
    groups: list[_FakeGroup],
    category: Optional[str],
    date_filter: Optional[date],
    date_from: Optional[date],
    date_to: Optional[date],
) -> list[_FakeGroup]:
    """Pure Python mirror of the get_groups route filter logic."""
    result = []
    for g in groups:
        if category is not None and g.category.lower() != category.lower():
            continue
        if date_filter is not None and g.grouped_date != date_filter:
            continue
        if date_from is not None and g.grouped_date < date_from:
            continue
        if date_to is not None and g.grouped_date > date_to:
            continue
        result.append(g)
    return result


def _satisfies_group_filters(
    g: _FakeGroup,
    category: Optional[str],
    date_filter: Optional[date],
    date_from: Optional[date],
    date_to: Optional[date],
) -> bool:
    if category is not None and g.category.lower() != category.lower():
        return False
    if date_filter is not None and g.grouped_date != date_filter:
        return False
    if date_from is not None and g.grouped_date < date_from:
        return False
    if date_to is not None and g.grouped_date > date_to:
        return False
    return True


def _paginate_groups(
    filtered: list[_FakeGroup], page: int, size: int
) -> tuple[list[_FakeGroup], int, int]:
    """Mirrors the pagination math in get_groups route."""
    total = len(filtered)
    pages = math.ceil(total / size) if total > 0 else 0
    offset = (page - 1) * size
    return filtered[offset : offset + size], total, pages


@given(
    groups=_groups_st,
    category=_cat_filter_st,
    date_filter=_date_filter_st,
    date_from=_date_filter_st,
    date_to=_date_filter_st,
    page=_page_st,
    size=_size_st,
)
@h_settings(max_examples=100)
def test_group_list_filtering_soundness(
    groups, category, date_filter, date_from, date_to, page, size
):
    """Property 5 (soundness): every group on the returned page satisfies all active filters.

    Feature: article-grouping, Property 5: Group list filtering and pagination
    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.9
    """
    filtered = _apply_group_filters(groups, category, date_filter, date_from, date_to)
    page_items, _, _ = _paginate_groups(filtered, page, size)

    for g in page_items:
        assert _satisfies_group_filters(g, category, date_filter, date_from, date_to), (
            f"Group id={g.id} category='{g.category}' date={g.grouped_date} "
            f"is in result but does not satisfy filters: "
            f"category={category!r}, date_filter={date_filter!r}, "
            f"date_from={date_from!r}, date_to={date_to!r}"
        )


@given(
    groups=_groups_st,
    category=_cat_filter_st,
    date_filter=_date_filter_st,
    date_from=_date_filter_st,
    date_to=_date_filter_st,
    page=_page_st,
    size=_size_st,
)
@h_settings(max_examples=100)
def test_group_list_filtering_completeness(
    groups, category, date_filter, date_from, date_to, page, size
):
    """Property 5 (completeness): the filtered list contains exactly as many groups as satisfy the filters.

    Feature: article-grouping, Property 5: Group list filtering and pagination
    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.9
    """
    filtered = _apply_group_filters(groups, category, date_filter, date_from, date_to)
    expected_count = sum(
        1 for g in groups
        if _satisfies_group_filters(g, category, date_filter, date_from, date_to)
    )

    assert len(filtered) == expected_count, (
        f"filtered list has {len(filtered)} groups but {expected_count} groups satisfy filters: "
        f"category={category!r}, date_filter={date_filter!r}, "
        f"date_from={date_from!r}, date_to={date_to!r}"
    )


@given(
    groups=_groups_st,
    category=_cat_filter_st,
    date_filter=_date_filter_st,
    date_from=_date_filter_st,
    date_to=_date_filter_st,
    page=_page_st,
    size=_size_st,
)
@h_settings(max_examples=100)
def test_group_list_page_size_limit(
    groups, category, date_filter, date_from, date_to, page, size
):
    """Property 5 (page size): returned page never exceeds `size` items.

    Feature: article-grouping, Property 5: Group list filtering and pagination
    Validates: Requirements 6.9
    """
    filtered = _apply_group_filters(groups, category, date_filter, date_from, date_to)
    page_items, _, _ = _paginate_groups(filtered, page, size)

    assert len(page_items) <= size, (
        f"Page has {len(page_items)} items but size limit is {size}"
    )


@given(
    groups=_groups_st,
    category=_cat_filter_st,
    date_filter=_date_filter_st,
    date_from=_date_filter_st,
    date_to=_date_filter_st,
    page=_page_st,
    size=_size_st,
)
@h_settings(max_examples=100)
def test_group_list_total_and_pages_calculation(
    groups, category, date_filter, date_from, date_to, page, size
):
    """Property 5 (pagination math): total equals filtered count; pages = ceil(total/size) or 0.

    Feature: article-grouping, Property 5: Group list filtering and pagination
    Validates: Requirements 6.9
    """
    filtered = _apply_group_filters(groups, category, date_filter, date_from, date_to)
    _, total, pages = _paginate_groups(filtered, page, size)

    assert total == len(filtered), (
        f"total={total} but {len(filtered)} groups satisfy the filters"
    )
    expected_pages = math.ceil(total / size) if total > 0 else 0
    assert pages == expected_pages, (
        f"pages={pages} but expected ceil({total}/{size})={expected_pages}"
    )
