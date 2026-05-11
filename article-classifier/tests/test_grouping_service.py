"""Property tests for grouping service logic.

Feature: article-grouping
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

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
