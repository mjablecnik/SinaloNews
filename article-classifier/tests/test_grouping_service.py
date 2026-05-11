"""Property tests and unit tests for grouping service logic.

Feature: article-grouping
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

from hypothesis import given, settings as h_settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Pure helpers that mirror GroupingService internals
# ---------------------------------------------------------------------------


@dataclass
class _FakeArticleTag:
    id: int
    tag_name: str
    tag_parent_name: Optional[str]  # None means the tag is a top-level category itself


@dataclass
class _FakeClassification:
    summary: Optional[str]
    article_tags: list[_FakeArticleTag] = field(default_factory=list)


@dataclass
class _FakeArticle:
    id: int
    published_at: Optional[datetime]
    classification: Optional[_FakeClassification]
    is_grouped: bool  # True if article_group_members row exists


def _is_candidate(article: _FakeArticle, target_date: date) -> bool:
    """Mirrors the WHERE clause in GroupingService.get_candidates().

    Conditions (all must hold):
    1. published_at date == target_date
    2. Has a ClassificationResult with a non-empty summary
    3. Not already a member of any ArticleGroup
    """
    if article.published_at is None:
        return False
    if article.published_at.date() != target_date:
        return False
    if article.classification is None:
        return False
    summary = article.classification.summary
    if summary is None or summary == "":
        return False
    if article.is_grouped:
        return False
    return True


def _get_category(article: _FakeArticle) -> Optional[str]:
    """Mirrors the category-derivation logic in GroupingService.get_candidates()."""
    cr = article.classification
    if cr is None or not cr.article_tags:
        return None
    # Pick the tag with the lowest id (same as min(..., key=lambda at: at.id))
    first_at = min(cr.article_tags, key=lambda at: at.id)
    if first_at.tag_parent_name is not None:
        return first_at.tag_parent_name
    return first_at.tag_name


def _select_candidates(
    articles: list[_FakeArticle], target_date: date
) -> list[_FakeArticle]:
    """Pure version of the get_candidates filter (without category grouping)."""
    return [a for a in articles if _is_candidate(a, target_date)]


def _partition_by_category(
    candidates: list[_FakeArticle],
) -> dict[str, list[_FakeArticle]]:
    """Mirrors the category partitioning in GroupingService.get_candidates()."""
    by_category: dict[str, list[_FakeArticle]] = defaultdict(list)
    for article in candidates:
        category = _get_category(article)
        if category is None:
            continue
        by_category[category].append(article)
    return dict(by_category)


def _apply_threshold_filter(
    partitioned: dict[str, list[_FakeArticle]],
    min_articles: int,
    max_articles: int,
) -> dict[str, list[_FakeArticle]]:
    """Mirrors the threshold logic in GroupingService.run_grouping().

    For each category: enforce max_articles limit first (keep first N, which
    mirrors 'most recent' after the DB query sorted desc), then skip categories
    below min_articles.
    """
    result: dict[str, list[_FakeArticle]] = {}
    for category, articles in partitioned.items():
        if len(articles) > max_articles:
            articles = articles[:max_articles]
        if len(articles) >= min_articles:
            result[category] = articles
    return result


def _truncate_to_most_recent(
    articles: list[_FakeArticle],
    max_articles: int,
) -> list[_FakeArticle]:
    """Mirrors the per-category truncation in GroupingService.run_grouping().

    The DB query returns articles sorted by published_at DESC (most recent first).
    This helper replicates that sort + slice so property tests can verify correctness
    independent of the DB ordering.

    Articles without published_at are placed after dated ones (treated as oldest).
    """
    dated = sorted(
        [a for a in articles if a.published_at is not None],
        key=lambda a: a.published_at,
        reverse=True,
    )
    undated = [a for a in articles if a.published_at is None]
    ordered = dated + undated
    return ordered[:max_articles]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

TARGET_DATE = date(2026, 5, 7)

_published_at_strategy = st.one_of(
    st.none(),
    # Target date with varying times
    st.datetimes(
        min_value=datetime(2026, 5, 7, 0, 0, 0),
        max_value=datetime(2026, 5, 7, 23, 59, 59),
    ),
    # Different date
    st.datetimes(
        min_value=datetime(2026, 5, 1, 0, 0, 0),
        max_value=datetime(2026, 5, 6, 23, 59, 59),
    ),
    st.datetimes(
        min_value=datetime(2026, 5, 8, 0, 0, 0),
        max_value=datetime(2026, 5, 14, 23, 59, 59),
    ),
)

_summary_strategy = st.one_of(
    st.none(),
    st.just(""),
    st.text(min_size=1, max_size=200),
)

_article_tag_strategy = st.builds(
    _FakeArticleTag,
    id=st.integers(min_value=1, max_value=1000),
    tag_name=st.sampled_from(["Technology", "Politics", "Economy", "Sport", "Culture"]),
    tag_parent_name=st.one_of(
        st.none(),
        st.sampled_from(["Technology", "Politics", "Economy"]),
    ),
)

_classification_strategy = st.one_of(
    st.none(),
    st.builds(
        _FakeClassification,
        summary=_summary_strategy,
        article_tags=st.lists(_article_tag_strategy, min_size=0, max_size=5),
    ),
)


def _article_strategy(article_id: int):
    return st.builds(
        _FakeArticle,
        id=st.just(article_id),
        published_at=_published_at_strategy,
        classification=_classification_strategy,
        is_grouped=st.booleans(),
    )


_articles_strategy = st.lists(
    st.integers(min_value=1, max_value=500).flatmap(_article_strategy),
    min_size=0,
    max_size=30,
    unique_by=lambda a: a.id,
)


# ---------------------------------------------------------------------------
# Feature: article-grouping, Property 1: Candidate selection correctness
# ---------------------------------------------------------------------------


@given(_articles_strategy)
@h_settings(max_examples=100)
def test_candidate_selection_correctness(articles):
    """Property 1: Candidate selection correctness.

    For any set of articles with varying published_at dates, classification
    states, summary presence, and group memberships, the candidate selection
    function returns exactly those articles satisfying all three conditions:
    (a) published_at on target_date, (b) non-empty summary exists, (c) not grouped.

    Validates: Requirements 1.1, 1.4
    """
    candidates = _select_candidates(articles, TARGET_DATE)
    candidate_ids = {a.id for a in candidates}

    for article in articles:
        should_be_candidate = (
            article.published_at is not None
            and article.published_at.date() == TARGET_DATE
            and article.classification is not None
            and article.classification.summary is not None
            and article.classification.summary != ""
            and not article.is_grouped
        )
        assert (article.id in candidate_ids) == should_be_candidate, (
            f"Article id={article.id} published_at={article.published_at} "
            f"summary={article.classification.summary if article.classification else None} "
            f"is_grouped={article.is_grouped}: "
            f"expected in_candidates={should_be_candidate}, got={article.id in candidate_ids}"
        )


@given(_articles_strategy)
@h_settings(max_examples=100)
def test_candidate_selection_no_missing_articles(articles):
    """Property 1 (completeness): every article meeting all conditions is included.

    Validates: Requirements 1.1, 1.4
    """
    candidates = _select_candidates(articles, TARGET_DATE)
    candidate_ids = {a.id for a in candidates}

    for article in articles:
        if (
            article.published_at is not None
            and article.published_at.date() == TARGET_DATE
            and article.classification is not None
            and article.classification.summary is not None
            and article.classification.summary != ""
            and not article.is_grouped
        ):
            assert article.id in candidate_ids, (
                f"Article id={article.id} should be a candidate but was excluded"
            )


@given(_articles_strategy)
@h_settings(max_examples=100)
def test_candidate_selection_no_extra_articles(articles):
    """Property 1 (soundness): every returned candidate truly meets all conditions.

    Validates: Requirements 1.1, 1.4
    """
    candidates = _select_candidates(articles, TARGET_DATE)

    for article in candidates:
        assert article.published_at is not None, "candidate must have published_at"
        assert article.published_at.date() == TARGET_DATE, "candidate must be on target_date"
        assert article.classification is not None, "candidate must have classification"
        assert article.classification.summary is not None, "candidate must have non-None summary"
        assert article.classification.summary != "", "candidate must have non-empty summary"
        assert not article.is_grouped, "candidate must not already be grouped"


# ---------------------------------------------------------------------------
# Feature: article-grouping, Property 2: Category partitioning correctness
# ---------------------------------------------------------------------------


@given(_articles_strategy)
@h_settings(max_examples=100)
def test_category_partitioning_no_article_in_multiple_buckets(articles):
    """Property 2 (exclusivity): no article appears in more than one category bucket.

    For any set of candidate articles, partitioning must produce disjoint buckets —
    each article belongs to at most one category.

    Validates: Requirements 1.2, 1.3
    """
    candidates = _select_candidates(articles, TARGET_DATE)
    partitioned = _partition_by_category(candidates)

    seen_ids: set[int] = set()
    for category, bucket in partitioned.items():
        for article in bucket:
            assert article.id not in seen_ids, (
                f"Article id={article.id} appeared in more than one category bucket "
                f"(duplicate found in '{category}')"
            )
            seen_ids.add(article.id)


@given(_articles_strategy)
@h_settings(max_examples=100)
def test_category_partitioning_correct_bucket_assignment(articles):
    """Property 2 (correctness): each article is placed in the right category bucket.

    Every article in a bucket must have _get_category() equal to that bucket's key.

    Validates: Requirements 1.2, 1.3
    """
    candidates = _select_candidates(articles, TARGET_DATE)
    partitioned = _partition_by_category(candidates)

    for category, bucket in partitioned.items():
        for article in bucket:
            expected_category = _get_category(article)
            assert expected_category == category, (
                f"Article id={article.id} placed in bucket '{category}' "
                f"but _get_category returns '{expected_category}'"
            )


@given(_articles_strategy)
@h_settings(max_examples=100)
def test_category_partitioning_all_categorisable_candidates_included(articles):
    """Property 2 (completeness): every candidate with a derivable category is in a bucket.

    No candidate that has at least one tag with a determinable category should be
    silently dropped from all buckets.

    Validates: Requirements 1.2, 1.3
    """
    candidates = _select_candidates(articles, TARGET_DATE)
    partitioned = _partition_by_category(candidates)

    all_bucketed_ids: set[int] = {a.id for bucket in partitioned.values() for a in bucket}

    for article in candidates:
        expected_category = _get_category(article)
        if expected_category is not None:
            assert article.id in all_bucketed_ids, (
                f"Article id={article.id} has category '{expected_category}' "
                f"but was not placed in any bucket"
            )


# ---------------------------------------------------------------------------
# Feature: article-grouping, Property 3: Minimum articles threshold
# ---------------------------------------------------------------------------

_threshold_strategy = st.integers(min_value=1, max_value=10)
_max_articles_strategy = st.integers(min_value=1, max_value=50)

# A partition is a dict category -> list[_FakeArticle] with 0-8 articles each
_partition_strategy = st.fixed_dictionaries(
    {},
    optional={
        cat: st.lists(
            st.integers(min_value=1, max_value=500).flatmap(_article_strategy),
            min_size=0,
            max_size=15,
        )
        for cat in ["Technology", "Politics", "Economy", "Sport", "Culture"]
    },
)


@given(_partition_strategy, _threshold_strategy, _max_articles_strategy)
@h_settings(max_examples=100)
def test_threshold_excludes_small_categories(partitioned, min_articles, max_articles):
    """Property 3 (soundness): no category below the threshold reaches clustering.

    After applying the max_articles cap, every category in the result must have
    at least min_articles articles — categories that fall short must be skipped.

    Validates: Requirements 1.5
    """
    result = _apply_threshold_filter(partitioned, min_articles, max_articles)

    for category, articles in result.items():
        assert len(articles) >= min_articles, (
            f"Category '{category}' has {len(articles)} articles but threshold is {min_articles}"
        )


@given(_partition_strategy, _threshold_strategy, _max_articles_strategy)
@h_settings(max_examples=100)
def test_threshold_includes_large_categories(partitioned, min_articles, max_articles):
    """Property 3 (completeness): every category meeting the threshold is included.

    A category that (after the max_articles cap) has at least min_articles articles
    must appear in the result — it must not be silently dropped.

    Validates: Requirements 1.5
    """
    result = _apply_threshold_filter(partitioned, min_articles, max_articles)

    for category, articles in partitioned.items():
        effective = articles[:max_articles] if len(articles) > max_articles else articles
        if len(effective) >= min_articles:
            assert category in result, (
                f"Category '{category}' has {len(effective)} articles (>= {min_articles}) "
                f"but was excluded from clustering"
            )


@given(_partition_strategy, _threshold_strategy, _max_articles_strategy)
@h_settings(max_examples=100)
def test_threshold_preserves_article_content(partitioned, min_articles, max_articles):
    """Property 3 (integrity): articles in passing categories are unchanged (except cap).

    The articles returned for each passing category must be exactly the first
    min(len, max_articles) articles from the original partition — no articles
    added, removed, or reordered beyond the cap.

    Validates: Requirements 1.5, 11.5
    """
    result = _apply_threshold_filter(partitioned, min_articles, max_articles)

    for category, articles in result.items():
        original = partitioned[category]
        expected = original[:max_articles] if len(original) > max_articles else original
        assert [a.id for a in articles] == [a.id for a in expected], (
            f"Category '{category}' articles were modified unexpectedly"
        )


# ---------------------------------------------------------------------------
# Feature: article-grouping, Property 9: Max articles per category truncation
# ---------------------------------------------------------------------------

_articles_with_dates_strategy = st.lists(
    st.integers(min_value=1, max_value=200).flatmap(
        lambda aid: st.builds(
            _FakeArticle,
            id=st.just(aid),
            published_at=st.one_of(
                st.none(),
                st.datetimes(
                    min_value=datetime(2026, 1, 1, 0, 0, 0),
                    max_value=datetime(2026, 12, 31, 23, 59, 59),
                ),
            ),
            classification=_classification_strategy,
            is_grouped=st.booleans(),
        )
    ),
    min_size=0,
    max_size=60,
)

_max_limit_strategy = st.integers(min_value=1, max_value=50)


@given(_articles_with_dates_strategy, _max_limit_strategy)
@h_settings(max_examples=100)
def test_truncation_count_never_exceeds_limit(articles, max_articles):
    """Property 9 (count bound): truncated list never exceeds max_articles.

    For any candidate list and any limit, the result must contain at most
    max_articles articles — never more.

    Validates: Requirements 11.5
    """
    result = _truncate_to_most_recent(articles, max_articles)
    assert len(result) <= max_articles, (
        f"Truncated list has {len(result)} articles but limit is {max_articles}"
    )


@given(_articles_with_dates_strategy, _max_limit_strategy)
@h_settings(max_examples=100)
def test_truncation_returns_all_when_below_limit(articles, max_articles):
    """Property 9 (no-op below limit): when count <= max, all articles are returned.

    If the input has at most max_articles items, nothing should be dropped.

    Validates: Requirements 11.5
    """
    if len(articles) > max_articles:
        return  # only test the below-limit case

    result = _truncate_to_most_recent(articles, max_articles)
    assert len(result) == len(articles), (
        f"Expected all {len(articles)} articles but got {len(result)}"
    )
    assert {a.id for a in result} == {a.id for a in articles}, (
        "Wrong articles returned when input is below limit"
    )


@given(_articles_with_dates_strategy, _max_limit_strategy)
@h_settings(max_examples=100)
def test_truncation_excluded_articles_are_oldest(articles, max_articles):
    """Property 9 (recency): articles kept are always more recent than those dropped.

    When truncation occurs, every kept article with a published_at must be at least
    as recent as every excluded article with a published_at.

    Validates: Requirements 11.5
    """
    if len(articles) <= max_articles:
        return  # truncation only matters when over the limit

    result = _truncate_to_most_recent(articles, max_articles)
    result_ids = {a.id for a in result}
    excluded = [a for a in articles if a.id not in result_ids]

    kept_dates = [a.published_at for a in result if a.published_at is not None]
    excluded_dates = [a.published_at for a in excluded if a.published_at is not None]

    if not kept_dates or not excluded_dates:
        return  # can't compare without dates on both sides

    min_kept = min(kept_dates)
    max_excluded = max(excluded_dates)
    assert min_kept >= max_excluded, (
        f"Kept article with published_at={min_kept} is older than "
        f"excluded article with published_at={max_excluded}"
    )


@given(_articles_with_dates_strategy, _max_limit_strategy)
@h_settings(max_examples=100)
def test_truncation_result_is_subset_of_input(articles, max_articles):
    """Property 9 (subset): every returned article was in the original input.

    Truncation must not fabricate new articles or change article identity.

    Validates: Requirements 11.5
    """
    result = _truncate_to_most_recent(articles, max_articles)
    input_ids = {a.id for a in articles}

    for article in result:
        assert article.id in input_ids, (
            f"Article id={article.id} in result was not in the original input"
        )


# ---------------------------------------------------------------------------
# Unit tests for the new RAG-based GroupingService
# ---------------------------------------------------------------------------

import pytest


def _make_mock_article(article_id: int, text: str = "some text", title: str = "Title") -> MagicMock:
    article = MagicMock()
    article.id = article_id
    article.extracted_text = text
    article.title = title
    article.published_at = datetime(2026, 5, 11, 10, 0)
    return article


def _make_mock_session() -> MagicMock:
    """Create a mock session where sync methods are MagicMock and async are AsyncMock."""
    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.rollback = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    return session


def _make_session_factory(session: MagicMock) -> MagicMock:
    """Return a mock that works as AsyncSessionFactory() context manager."""
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=session)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=mock_ctx)


def _make_service():
    """Construct GroupingService with all external deps mocked out."""
    with patch("src.grouping_service.AsyncQdrantClient"), \
         patch("src.grouping_service.GroupingPipeline"):
        from src.grouping_service import GroupingService
        service = GroupingService()

    service._embedding_client = AsyncMock()
    service._similarity_service = AsyncMock()
    service._similarity_service.ensure_collection = AsyncMock()
    service._similarity_service.upsert_article = AsyncMock()
    service._similarity_service.find_most_similar = AsyncMock(return_value=None)
    service._pipeline = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_run_grouping_returns_zero_when_no_candidates():
    """Grouping with no unindexed candidates returns zero stats."""
    service = _make_service()

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=execute_result)

    factory = _make_session_factory(mock_session)
    with patch("src.grouping_service.AsyncSessionFactory", factory):
        result = await service.run_grouping(date(2026, 5, 11))

    assert result.groups_created == 0
    assert result.groups_updated == 0
    assert result.articles_grouped == 0
    assert result.date == date(2026, 5, 11)


@pytest.mark.asyncio
async def test_run_grouping_skips_article_with_empty_extracted_text():
    """Articles with empty extracted_text are skipped; embedding is never called."""
    service = _make_service()
    article = _make_mock_article(1, text="")

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [article]
    mock_session.execute = AsyncMock(return_value=execute_result)

    factory = _make_session_factory(mock_session)
    with patch("src.grouping_service.AsyncSessionFactory", factory):
        result = await service.run_grouping(date(2026, 5, 11))

    service._embedding_client.embed_text.assert_not_called()
    assert result.articles_grouped == 0


@pytest.mark.asyncio
async def test_run_grouping_skips_article_on_embedding_failure():
    """Embedding failure for one article causes it to be skipped; processing continues."""
    from src.embedding_client import EmbeddingError

    service = _make_service()
    article = _make_mock_article(1, text="good text")
    service._embedding_client.embed_text = AsyncMock(side_effect=EmbeddingError("API error"))

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [article]
    mock_session.execute = AsyncMock(return_value=execute_result)

    factory = _make_session_factory(mock_session)
    with patch("src.grouping_service.AsyncSessionFactory", factory):
        result = await service.run_grouping(date(2026, 5, 11))

    service._similarity_service.upsert_article.assert_not_called()
    assert result.articles_grouped == 0


@pytest.mark.asyncio
async def test_run_grouping_below_threshold_leaves_article_standalone():
    """An article whose best match is below the threshold is left ungrouped."""
    service = _make_service()
    article = _make_mock_article(1, text="some text")

    service._embedding_client.embed_text = AsyncMock(return_value=[0.1, 0.2])
    service._similarity_service.find_most_similar = AsyncMock(return_value=(99, 0.3))

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [article]
    mock_session.execute = AsyncMock(return_value=execute_result)

    factory = _make_session_factory(mock_session)
    with patch("src.grouping_service.AsyncSessionFactory", factory), \
         patch("src.grouping_service.settings") as mock_settings:
        mock_settings.GROUPING_SIMILARITY_THRESHOLD = 0.75
        mock_settings.EMBEDDING_API_URL = "http://test"
        mock_settings.OPENROUTER_API_KEY = "key"
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.QDRANT_URL = "http://qdrant"
        mock_settings.QDRANT_API_KEY = None
        mock_settings.QDRANT_FULL_ARTICLE_COLLECTION = "article_full"
        mock_settings.GROUPING_LLM_MODEL = None
        mock_settings.LLM_MODEL = "gpt"
        result = await service.run_grouping(date(2026, 5, 11))

    assert result.groups_created == 0
    assert result.groups_updated == 0


@pytest.mark.asyncio
async def test_run_grouping_creates_new_group_when_match_is_ungrouped():
    """When match is above threshold and ungrouped, a new group is created with both articles."""
    service = _make_service()
    article = _make_mock_article(1, text="some text")

    service._embedding_client.embed_text = AsyncMock(return_value=[0.1, 0.2])
    service._similarity_service.find_most_similar = AsyncMock(return_value=(99, 0.9))

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [article]
    mock_session.execute = AsyncMock(return_value=execute_result)

    with patch.object(service, "_get_group_for_article", AsyncMock(return_value=None)), \
         patch.object(service, "_is_article_in_any_group", AsyncMock(return_value=False)):
        factory = _make_session_factory(mock_session)
        with patch("src.grouping_service.AsyncSessionFactory", factory), \
             patch("src.grouping_service.settings") as mock_settings:
            mock_settings.GROUPING_SIMILARITY_THRESHOLD = 0.75
            mock_settings.EMBEDDING_API_URL = "http://test"
            mock_settings.OPENROUTER_API_KEY = "key"
            mock_settings.EMBEDDING_MODEL = "test-model"
            mock_settings.QDRANT_URL = "http://qdrant"
            mock_settings.QDRANT_API_KEY = None
            mock_settings.QDRANT_FULL_ARTICLE_COLLECTION = "article_full"
            mock_settings.GROUPING_LLM_MODEL = None
            mock_settings.LLM_MODEL = "gpt"
            result = await service.run_grouping(date(2026, 5, 11))

    assert result.groups_created == 1
    assert result.articles_grouped == 1


@pytest.mark.asyncio
async def test_run_grouping_adds_article_to_existing_group():
    """When match is in an existing group, the article is added to that group."""
    service = _make_service()
    article = _make_mock_article(2, text="some text")

    service._embedding_client.embed_text = AsyncMock(return_value=[0.5, 0.5])
    service._similarity_service.find_most_similar = AsyncMock(return_value=(1, 0.95))

    mock_group = MagicMock()
    mock_group.id = 42
    mock_group.members = []  # No existing members with same article_id
    mock_group.grouped_date = date(2026, 5, 11)
    mock_group.needs_regeneration = False

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [article]
    mock_session.execute = AsyncMock(return_value=execute_result)

    with patch.object(service, "_get_group_for_article", AsyncMock(return_value=mock_group)):
        factory = _make_session_factory(mock_session)
        with patch("src.grouping_service.AsyncSessionFactory", factory), \
             patch("src.grouping_service.settings") as mock_settings:
            mock_settings.GROUPING_SIMILARITY_THRESHOLD = 0.75
            mock_settings.EMBEDDING_API_URL = "http://test"
            mock_settings.OPENROUTER_API_KEY = "key"
            mock_settings.EMBEDDING_MODEL = "test-model"
            mock_settings.QDRANT_URL = "http://qdrant"
            mock_settings.QDRANT_API_KEY = None
            mock_settings.QDRANT_FULL_ARTICLE_COLLECTION = "article_full"
            mock_settings.GROUPING_LLM_MODEL = None
            mock_settings.LLM_MODEL = "gpt"
            result = await service.run_grouping(date(2026, 5, 11))

    assert result.groups_updated == 1
    assert result.articles_grouped == 1
    assert mock_group.needs_regeneration is True


@pytest.mark.asyncio
async def test_run_regeneration_processes_flagged_groups():
    """run_regeneration calls generate_detail for groups with needs_regeneration=True."""
    from src.grouping_schemas import GroupDetailOutput

    service = _make_service()

    mock_article = _make_mock_article(10, text="article text")
    mock_member = MagicMock()
    mock_member.article = mock_article

    mock_group = MagicMock()
    mock_group.id = 1
    mock_group.members = [mock_member]

    service._pipeline.generate_detail = AsyncMock(
        return_value=GroupDetailOutput(title="T", summary="S", detail="D")
    )

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [mock_group]
    mock_session.execute = AsyncMock(return_value=execute_result)

    mock_db_group = MagicMock()
    mock_db_group.id = 1
    mock_db_group.needs_regeneration = True
    mock_session.get = AsyncMock(return_value=mock_db_group)

    factory = _make_session_factory(mock_session)
    with patch("src.grouping_service.AsyncSessionFactory", factory):
        result = await service.run_regeneration()

    service._pipeline.generate_detail.assert_called_once()
    assert mock_db_group.needs_regeneration is False
    assert mock_db_group.title == "T"
    assert result.groups_regenerated == 1


@pytest.mark.asyncio
async def test_run_regeneration_leaves_flag_set_on_llm_failure():
    """When generate_detail raises, needs_regeneration is NOT cleared."""
    service = _make_service()

    mock_article = _make_mock_article(10, text="article text")
    mock_member = MagicMock()
    mock_member.article = mock_article

    mock_group = MagicMock()
    mock_group.id = 1
    mock_group.members = [mock_member]

    service._pipeline.generate_detail = AsyncMock(side_effect=RuntimeError("LLM error"))

    mock_session = _make_mock_session()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [mock_group]
    mock_session.execute = AsyncMock(return_value=execute_result)

    factory = _make_session_factory(mock_session)
    with patch("src.grouping_service.AsyncSessionFactory", factory):
        result = await service.run_regeneration()

    # group was NOT updated since generate_detail failed
    mock_session.get.assert_not_called()
    assert result.groups_regenerated == 0
