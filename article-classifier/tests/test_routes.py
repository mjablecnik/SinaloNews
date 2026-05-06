"""Property tests for API behavior.

Feature: article-classifier
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from hypothesis import given
from hypothesis import strategies as st

from src.constants import ContentType, TAG_TAXONOMY

_ALL_CONTENT_TYPES = [ct.value for ct in ContentType]
_ALL_CATEGORIES = list(TAG_TAXONOMY.keys())
_ALL_TAG_PAIRS = [(cat, sub) for cat, subs in TAG_TAXONOMY.items() for sub in subs]

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
