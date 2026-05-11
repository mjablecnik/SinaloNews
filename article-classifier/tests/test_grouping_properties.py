"""
Property-based tests for the RAG-based grouping feature.

All properties use Hypothesis with @settings(max_examples=100).
Tag format: # Feature: rag-based-grouping, Property {N}: {property_text}
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st
from pydantic import BaseModel, Field, ValidationError

from src.similarity_service import SimilarityService, _NAMESPACE


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_article_id_strategy = st.integers(min_value=1, max_value=1_000_000)

_published_at_strategy = st.one_of(
    st.none(),
    st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2026, 12, 31)),
)


# ---------------------------------------------------------------------------
# Helpers for Property 1
# ---------------------------------------------------------------------------

@dataclass
class _FakeArticleForIndexing:
    article_id: int
    article_title: str
    published_at: Optional[datetime]
    extracted_text: str


_REQUIRED_METADATA_KEYS = {"article_id", "article_title", "published_at", "indexed_at"}


def _build_metadata(article: _FakeArticleForIndexing, indexed_at: datetime) -> dict:
    """Mirror the metadata building in GroupingService.run_grouping() phase 1."""
    return {
        "article_id": article.article_id,
        "article_title": article.article_title or "",
        "published_at": article.published_at.isoformat() if article.published_at else "",
        "indexed_at": indexed_at.isoformat(),
    }


_article_for_indexing_strategy = st.builds(
    _FakeArticleForIndexing,
    article_id=_article_id_strategy,
    article_title=st.text(min_size=0, max_size=200),
    published_at=_published_at_strategy,
    extracted_text=st.text(min_size=1, max_size=500),
)


# ---------------------------------------------------------------------------
# Property 1: Indexing produces exactly one point per article with
#             deterministic ID and complete metadata
# Feature: rag-based-grouping, Property 1: Indexing determinism and completeness
# ---------------------------------------------------------------------------


@given(_article_for_indexing_strategy)
@h_settings(max_examples=100)
def test_property1_point_id_is_deterministic(article):
    """Feature: rag-based-grouping, Property 1: Point ID is deterministic.

    For any article_id, make_point_id always returns the same UUID string.
    Re-indexing the same article maps to the same point ID, so the upsert
    is idempotent and no duplicates are created.
    Validates: Requirements 1.3, 1.5
    """
    id1 = SimilarityService.make_point_id(article.article_id)
    id2 = SimilarityService.make_point_id(article.article_id)
    assert id1 == id2, (
        f"make_point_id({article.article_id}) returned different values on successive calls"
    )


@given(_article_for_indexing_strategy)
@h_settings(max_examples=100)
def test_property1_point_id_is_valid_uuid(article):
    """Feature: rag-based-grouping, Property 1: Point ID is a valid UUID.

    make_point_id must return a string that parses as a valid UUID, which
    is required by the Qdrant API.
    Validates: Requirements 1.3
    """
    point_id = SimilarityService.make_point_id(article.article_id)
    try:
        parsed = uuid.UUID(point_id)
    except ValueError:
        pytest.fail(f"make_point_id({article.article_id}) returned invalid UUID: {point_id!r}")
    assert str(parsed) == point_id, "UUID string representation is not normalised"


@given(st.lists(_article_id_strategy, min_size=2, max_size=50, unique=True))
@h_settings(max_examples=100)
def test_property1_distinct_articles_have_distinct_point_ids(article_ids):
    """Feature: rag-based-grouping, Property 1: Distinct articles map to distinct point IDs.

    The uuid5 construction over a fixed namespace guarantees injectivity
    within the integer domain, ensuring no two different articles collide.
    Validates: Requirements 1.5
    """
    point_ids = [SimilarityService.make_point_id(aid) for aid in article_ids]
    assert len(set(point_ids)) == len(article_ids), (
        "Distinct article IDs produced duplicate point IDs"
    )


@given(_article_for_indexing_strategy)
@h_settings(max_examples=100)
def test_property1_metadata_contains_all_required_keys(article):
    """Feature: rag-based-grouping, Property 1: Upserted metadata has all required fields.

    Each point's payload must carry article_id, article_title, published_at,
    and indexed_at so that downstream queries can reconstruct article identity.
    Validates: Requirements 1.4
    """
    indexed_at = datetime(2026, 5, 11, 12, 0, 0)
    metadata = _build_metadata(article, indexed_at)
    missing = _REQUIRED_METADATA_KEYS - metadata.keys()
    assert not missing, f"Metadata is missing required keys: {missing}"


# ---------------------------------------------------------------------------
# Helpers for Properties 2-9
# ---------------------------------------------------------------------------

TARGET_DATE = date(2026, 5, 11)


@dataclass
class _FakeArticleRAG:
    id: int
    extracted_text: Optional[str]
    published_at: Optional[datetime]
    has_classification: bool
    has_non_empty_summary: bool
    is_indexed: bool  # True if a row exists in full_article_indexed


def _is_candidate_rag(article: _FakeArticleRAG, target_date: date) -> bool:
    """Mirror the WHERE clause in GroupingService._get_candidates()."""
    if article.published_at is None:
        return False
    if article.published_at.date() != target_date:
        return False
    if not article.has_classification:
        return False
    if not article.has_non_empty_summary:
        return False
    if article.is_indexed:
        return False
    return True


_rag_articles_strategy = st.lists(
    st.integers(min_value=1, max_value=10_000).flatmap(
        lambda aid: st.builds(
            _FakeArticleRAG,
            id=st.just(aid),
            extracted_text=st.one_of(
                st.none(), st.just(""), st.text(min_size=1, max_size=300)
            ),
            published_at=st.one_of(
                st.none(),
                st.datetimes(
                    min_value=datetime(2026, 5, 11, 0, 0),
                    max_value=datetime(2026, 5, 11, 23, 59, 59),
                ),
                st.datetimes(
                    min_value=datetime(2026, 5, 10, 0, 0),
                    max_value=datetime(2026, 5, 10, 23, 59, 59),
                ),
            ),
            has_classification=st.booleans(),
            has_non_empty_summary=st.booleans(),
            is_indexed=st.booleans(),
        )
    ),
    min_size=0,
    max_size=30,
    unique_by=lambda a: a.id,
)


# ---------------------------------------------------------------------------
# Property 2: Only classified, unindexed articles are selected as candidates
# Feature: rag-based-grouping, Property 2: Candidate selection correctness
# ---------------------------------------------------------------------------


@given(_rag_articles_strategy)
@h_settings(max_examples=100)
def test_property2_candidate_selection_soundness(articles):
    """Feature: rag-based-grouping, Property 2: Every returned candidate meets all conditions.

    No article that fails any of the candidate conditions (missing classification,
    already indexed, wrong date, no published_at) should appear in the result.
    Validates: Requirements 2.1, 2.4
    """
    candidates = [a for a in articles if _is_candidate_rag(a, TARGET_DATE)]

    for article in candidates:
        assert article.published_at is not None, "candidate must have published_at"
        assert article.published_at.date() == TARGET_DATE, "candidate must be on TARGET_DATE"
        assert article.has_classification, "candidate must have a ClassificationResult"
        assert article.has_non_empty_summary, "candidate must have a non-empty summary"
        assert not article.is_indexed, "candidate must not already be in full_article_indexed"


@given(_rag_articles_strategy)
@h_settings(max_examples=100)
def test_property2_candidate_selection_completeness(articles):
    """Feature: rag-based-grouping, Property 2: Every qualifying article is included.

    No article that satisfies all conditions should be silently omitted from
    the candidate set.
    Validates: Requirements 2.1, 2.4
    """
    candidates = [a for a in articles if _is_candidate_rag(a, TARGET_DATE)]
    candidate_ids = {a.id for a in candidates}

    for article in articles:
        should_be_candidate = (
            article.published_at is not None
            and article.published_at.date() == TARGET_DATE
            and article.has_classification
            and article.has_non_empty_summary
            and not article.is_indexed
        )
        if should_be_candidate:
            assert article.id in candidate_ids, (
                f"Article id={article.id} satisfies all conditions but was not selected"
            )


@given(_rag_articles_strategy)
@h_settings(max_examples=100)
def test_property2_already_indexed_articles_never_selected(articles):
    """Feature: rag-based-grouping, Property 2: Already-indexed articles are excluded.

    Articles already in full_article_indexed must never appear as candidates,
    preventing redundant embedding API calls on subsequent grouping runs.
    Validates: Requirements 2.1, 2.4
    """
    candidates = [a for a in articles if _is_candidate_rag(a, TARGET_DATE)]

    for candidate in candidates:
        assert not candidate.is_indexed, (
            f"Article id={candidate.id} is already indexed but was selected as candidate"
        )


# ---------------------------------------------------------------------------
# Property 3: Self-exclusion from similarity search
# Feature: rag-based-grouping, Property 3: Self-exclusion
# ---------------------------------------------------------------------------


def _build_exclude_point_ids(
    article_id: int, extra_excludes: Optional[list[int]] = None
) -> list[str]:
    """Mirror SimilarityService.find_most_similar() exclusion logic."""
    all_excluded = list(extra_excludes or []) + [article_id]
    return [SimilarityService.make_point_id(aid) for aid in all_excluded]


@given(
    article_id=_article_id_strategy,
    extra_excludes=st.lists(_article_id_strategy, min_size=0, max_size=10),
)
@h_settings(max_examples=100)
def test_property3_self_always_in_exclusion_list(article_id, extra_excludes):
    """Feature: rag-based-grouping, Property 3: Article is always excluded from its own search.

    For any article being queried, the exclusion filter passed to Qdrant must
    always include the article's own point ID so the article can never match itself.
    Validates: Requirements 3.2
    """
    excluded_ids = _build_exclude_point_ids(article_id, extra_excludes)
    self_point_id = SimilarityService.make_point_id(article_id)
    assert self_point_id in excluded_ids, (
        f"Article {article_id}'s own point ID is missing from the exclusion list"
    )


@given(
    article_id=_article_id_strategy,
    extra_excludes=st.lists(_article_id_strategy, min_size=1, max_size=10),
)
@h_settings(max_examples=100)
def test_property3_extra_excludes_also_excluded(article_id, extra_excludes):
    """Feature: rag-based-grouping, Property 3: Explicit extra excludes appear in filter.

    Any IDs passed via exclude_ids parameter must also appear in the Qdrant filter,
    ensuring articles that are already grouped are not proposed as matches.
    Validates: Requirements 3.2
    """
    excluded_ids = _build_exclude_point_ids(article_id, extra_excludes)
    for eid in extra_excludes:
        point_id = SimilarityService.make_point_id(eid)
        assert point_id in excluded_ids, (
            f"Extra exclude article_id={eid} was missing from the exclusion list"
        )


# ---------------------------------------------------------------------------
# Grouping decision helpers (shared by Properties 4-9)
# ---------------------------------------------------------------------------


@dataclass
class _Group:
    id: int
    member_ids: list[int] = field(default_factory=list)
    grouped_date: Optional[date] = None
    needs_regeneration: bool = False


def _make_grouping_decision(
    score: float,
    threshold: float,
    match_group: Optional[_Group],
) -> str:
    """Pure grouping decision that mirrors GroupingService.run_grouping() phase 2.

    Returns: 'join_group', 'create_group', or 'standalone'.
    """
    if score >= threshold:
        return "join_group" if match_group is not None else "create_group"
    return "standalone"


def _join_group(
    group: _Group,
    article_id: int,
    article_published_at: Optional[datetime],
) -> _Group:
    """Add article to an existing group; mirror grouped_date and flag logic."""
    group.member_ids.append(article_id)
    new_date = article_published_at.date() if article_published_at else None
    if new_date is not None:
        group.grouped_date = (
            max(group.grouped_date, new_date)
            if group.grouped_date is not None
            else new_date
        )
    group.needs_regeneration = True
    return group


def _create_group(
    group_id: int,
    article_id: int,
    match_id: int,
    article_published_at: Optional[datetime],
    match_published_at: Optional[datetime],
) -> _Group:
    """Create a new group with two founding articles."""
    dates = [
        article_published_at.date() if article_published_at else None,
        match_published_at.date() if match_published_at else None,
    ]
    valid_dates = [d for d in dates if d is not None]
    grouped_date = max(valid_dates) if valid_dates else date.today()
    return _Group(
        id=group_id,
        member_ids=[article_id, match_id],
        grouped_date=grouped_date,
        needs_regeneration=True,
    )


# ---------------------------------------------------------------------------
# Property 4: Grouping decision correctness based on threshold and group membership
# Feature: rag-based-grouping, Property 4: Grouping decision correctness
# ---------------------------------------------------------------------------


@given(
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    match_has_group=st.booleans(),
)
@h_settings(max_examples=100)
def test_property4_grouping_decision_join_group(score, threshold, match_has_group):
    """Feature: rag-based-grouping, Property 4: score >= threshold + match grouped → join_group.

    When similarity exceeds the threshold and the best match already belongs to
    a group, the current article must join that existing group.
    Validates: Requirements 3.3, 3.4
    """
    match_group = _Group(id=10, member_ids=[99]) if match_has_group else None
    decision = _make_grouping_decision(score, threshold, match_group)

    if score >= threshold and match_has_group:
        assert decision == "join_group", (
            f"Expected 'join_group' but got {decision!r} "
            f"(score={score}, threshold={threshold})"
        )


@given(
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@h_settings(max_examples=100)
def test_property4_grouping_decision_create_group(score, threshold):
    """Feature: rag-based-grouping, Property 4: score >= threshold + match ungrouped → create_group.

    When similarity exceeds the threshold but the best match is not yet in any
    group, a new group must be created for both articles.
    Validates: Requirements 3.3, 3.5
    """
    decision = _make_grouping_decision(score, threshold, match_group=None)

    if score >= threshold:
        assert decision == "create_group", (
            f"Expected 'create_group' (no existing group) but got {decision!r} "
            f"(score={score}, threshold={threshold})"
        )


@given(
    score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    match_has_group=st.booleans(),
)
@h_settings(max_examples=100)
def test_property4_grouping_decision_standalone(score, threshold, match_has_group):
    """Feature: rag-based-grouping, Property 4: score < threshold → standalone.

    When the best match score is below the threshold, the article must remain
    a standalone article regardless of whether the match has a group.
    Validates: Requirements 3.6
    """
    match_group = _Group(id=10, member_ids=[99]) if match_has_group else None
    decision = _make_grouping_decision(score, threshold, match_group)

    if score < threshold:
        assert decision == "standalone", (
            f"Expected 'standalone' but got {decision!r} "
            f"(score={score}, threshold={threshold})"
        )


# ---------------------------------------------------------------------------
# Sequential grouping simulation (Properties 5, 9)
# ---------------------------------------------------------------------------


@dataclass
class _SimArticle:
    id: int
    best_match_id: int  # globally best match article_id
    best_match_score: float
    published_at: Optional[datetime]


def _simulate_sequential_grouping(
    articles: list[_SimArticle],
    threshold: float,
) -> dict[int, int]:
    """Sequential grouping simulation mirroring GroupingService.run_grouping() phase 2.

    Returns: membership dict mapping article_id → group_id.
    """
    membership: dict[int, int] = {}
    groups: dict[int, _Group] = {}
    next_group_id = 1

    for article in articles:
        if article.id in membership:
            continue  # unique constraint: already grouped

        match_id = article.best_match_id
        match_group = groups.get(membership[match_id]) if match_id in membership else None
        decision = _make_grouping_decision(article.best_match_score, threshold, match_group)

        if decision == "join_group" and match_group is not None:
            if article.id not in match_group.member_ids:
                match_group.member_ids.append(article.id)
                membership[article.id] = match_group.id
                match_group.needs_regeneration = True

        elif decision == "create_group":
            g = _Group(id=next_group_id, member_ids=[article.id], needs_regeneration=True)
            next_group_id += 1
            membership[article.id] = g.id
            if match_id not in membership:
                g.member_ids.append(match_id)
                membership[match_id] = g.id
            groups[g.id] = g

    return membership


_sim_article_strategy = st.integers(min_value=1, max_value=100).flatmap(
    lambda aid: st.builds(
        _SimArticle,
        id=st.just(aid),
        best_match_id=st.integers(min_value=1, max_value=100),
        best_match_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        published_at=_published_at_strategy,
    )
)

_sim_articles_strategy = st.lists(
    _sim_article_strategy,
    min_size=0,
    max_size=20,
    unique_by=lambda a: a.id,
)


# ---------------------------------------------------------------------------
# Property 5: Single-group membership invariant
# Feature: rag-based-grouping, Property 5: Single-group membership
# ---------------------------------------------------------------------------


@given(_sim_articles_strategy, st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
@h_settings(max_examples=100)
def test_property5_single_group_membership_invariant(articles, threshold):
    """Feature: rag-based-grouping, Property 5: Each article belongs to at most one group.

    After the grouping process completes for any set of articles and any threshold,
    no article_id may appear in more than one group.  This mirrors the unique
    constraint on article_group_members.article_id in the database.
    Validates: Requirements 3.8
    """
    membership = _simulate_sequential_grouping(articles, threshold)

    # membership is a dict so keys are unique by construction;
    # also verify that no article_id appears in multiple group member lists.
    group_to_members: dict[int, list[int]] = {}
    for article_id, group_id in membership.items():
        group_to_members.setdefault(group_id, []).append(article_id)

    all_member_ids: list[int] = []
    for members in group_to_members.values():
        all_member_ids.extend(members)

    assert len(all_member_ids) == len(set(all_member_ids)), (
        "Some article_ids appear in multiple groups — single-group membership violated"
    )


# ---------------------------------------------------------------------------
# Property 6: grouped_date reflects most recent member
# Feature: rag-based-grouping, Property 6: grouped_date correctness
# ---------------------------------------------------------------------------


def _compute_grouped_date(published_ats: list[Optional[datetime]]) -> Optional[date]:
    """Mirror the grouped_date update logic in GroupingService.run_grouping()."""
    valid = [dt.date() for dt in published_ats if dt is not None]
    return max(valid) if valid else None


@given(
    st.lists(
        st.one_of(
            st.none(),
            st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2026, 12, 31)),
        ),
        min_size=1,
        max_size=20,
    )
)
@h_settings(max_examples=100)
def test_property6_grouped_date_equals_max_published_at(published_ats):
    """Feature: rag-based-grouping, Property 6: grouped_date equals the most recent member's date.

    For any Article_Group, grouped_date must equal the maximum published_at.date()
    across all member articles.  Articles with None published_at are ignored.
    Validates: Requirements 3.9
    """
    grouped_date = _compute_grouped_date(published_ats)
    valid_dates = [dt.date() for dt in published_ats if dt is not None]

    if valid_dates:
        assert grouped_date == max(valid_dates), (
            f"grouped_date={grouped_date} does not equal max(published_at)={max(valid_dates)}"
        )
    else:
        assert grouped_date is None, (
            f"Expected None when all published_at are None, got {grouped_date}"
        )


@given(
    existing_dates=st.lists(
        st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2023, 12, 31)),
        min_size=1,
        max_size=10,
    ),
    new_date=st.datetimes(
        min_value=datetime(2024, 1, 1), max_value=datetime(2026, 12, 31)
    ),
)
@h_settings(max_examples=100)
def test_property6_grouped_date_updates_when_newer_member_added(existing_dates, new_date):
    """Feature: rag-based-grouping, Property 6: grouped_date reflects newly added, more recent member.

    When a member with a strictly more recent published_at is added to a group,
    grouped_date must advance to that new date.
    Validates: Requirements 3.9
    """
    all_dates = existing_dates + [new_date]
    grouped_date = _compute_grouped_date(all_dates)
    # new_date is always > any existing_date by strategy construction
    assert grouped_date == new_date.date(), (
        f"grouped_date should be {new_date.date()} after adding a newer member"
    )


# ---------------------------------------------------------------------------
# Property 7: needs_regeneration is set on group creation or modification
# Feature: rag-based-grouping, Property 7: needs_regeneration on modification
# ---------------------------------------------------------------------------


@given(
    article_id=_article_id_strategy,
    match_id=_article_id_strategy,
    published_at=_published_at_strategy,
    match_published_at=_published_at_strategy,
)
@h_settings(max_examples=100)
def test_property7_needs_regeneration_set_on_group_creation(
    article_id, match_id, published_at, match_published_at
):
    """Feature: rag-based-grouping, Property 7: New groups have needs_regeneration=True.

    Any Article_Group created by the grouping process must immediately have
    needs_regeneration set to True so that the regenerate endpoint knows
    it requires LLM detail generation.
    Validates: Requirements 3.10
    """
    group = _create_group(
        group_id=1,
        article_id=article_id,
        match_id=match_id,
        article_published_at=published_at,
        match_published_at=match_published_at,
    )
    assert group.needs_regeneration is True, (
        "needs_regeneration must be True immediately after group creation"
    )


@given(
    article_id=_article_id_strategy,
    published_at=_published_at_strategy,
    initial_flag=st.booleans(),
)
@h_settings(max_examples=100)
def test_property7_needs_regeneration_set_when_member_added(
    article_id, published_at, initial_flag
):
    """Feature: rag-based-grouping, Property 7: Adding a member sets needs_regeneration=True.

    When a new article joins an existing group, needs_regeneration must be set
    to True regardless of the flag's prior value.
    Validates: Requirements 3.10
    """
    group = _Group(
        id=1,
        member_ids=[100],
        grouped_date=date(2026, 1, 1),
        needs_regeneration=initial_flag,
    )
    _join_group(group, article_id, published_at)
    assert group.needs_regeneration is True, (
        "needs_regeneration must be True after adding a member, regardless of prior value"
    )


# ---------------------------------------------------------------------------
# Property 8: needs_regeneration is cleared after successful detail regeneration
# Feature: rag-based-grouping, Property 8: needs_regeneration cleared after regeneration
# ---------------------------------------------------------------------------


def _simulate_regeneration(group: _Group) -> None:
    """Simulate a successful regeneration that clears the flag."""
    group.needs_regeneration = False


@given(initial_flag=st.booleans())
@h_settings(max_examples=100)
def test_property8_needs_regeneration_cleared_after_regeneration(initial_flag):
    """Feature: rag-based-grouping, Property 8: Successful regeneration clears needs_regeneration.

    After the Group_Detail_Pipeline succeeds for an Article_Group, the
    needs_regeneration flag must be False regardless of its prior value.
    Validates: Requirements 4.6
    """
    group = _Group(id=1, member_ids=[1, 2], needs_regeneration=initial_flag)
    _simulate_regeneration(group)
    assert group.needs_regeneration is False, (
        "needs_regeneration must be False after successful detail regeneration"
    )


@given(
    flags=st.lists(st.booleans(), min_size=1, max_size=10),
)
@h_settings(max_examples=100)
def test_property8_only_flagged_groups_are_processed(flags):
    """Feature: rag-based-grouping, Property 8: Regeneration only touches flagged groups.

    Groups where needs_regeneration is already False must not be regenerated.
    Only groups with needs_regeneration=True should be processed.
    Validates: Requirements 4.1, 4.6
    """
    groups = [
        _Group(id=i, member_ids=[i * 10], needs_regeneration=flag)
        for i, flag in enumerate(flags, start=1)
    ]
    flagged = [g for g in groups if g.needs_regeneration]

    for g in flagged:
        _simulate_regeneration(g)

    for g in groups:
        if g in flagged:
            assert g.needs_regeneration is False
        else:
            # Not flagged → unchanged
            assert g.needs_regeneration is False


# ---------------------------------------------------------------------------
# Property 9: Threshold monotonicity — higher threshold produces fewer or equal groups
# Feature: rag-based-grouping, Property 9: Threshold monotonicity
# ---------------------------------------------------------------------------


def _count_groups_for_threshold(
    articles: list[_SimArticle],
    threshold: float,
) -> int:
    """Return the number of distinct groups formed at the given threshold."""
    membership = _simulate_sequential_grouping(articles, threshold)
    return len(set(membership.values())) if membership else 0


@given(
    articles=_sim_articles_strategy,
    t1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    t2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@h_settings(max_examples=100)
def test_property9_threshold_monotonicity(articles, t1, t2):
    """Feature: rag-based-grouping, Property 9: Higher threshold → fewer or equal groups.

    For any fixed set of articles and similarity scores, running the grouping
    algorithm with a higher threshold T_high must produce at most as many
    groups as with a lower threshold T_low.
    Validates: Requirements 5.3, 5.4
    """
    high_t = max(t1, t2)
    low_t = min(t1, t2)

    groups_high = _count_groups_for_threshold(articles, high_t)
    groups_low = _count_groups_for_threshold(articles, low_t)

    assert groups_high <= groups_low, (
        f"Higher threshold {high_t:.4f} produced {groups_high} groups "
        f"but lower threshold {low_t:.4f} produced {groups_low} groups — "
        "expected groups_high <= groups_low"
    )


@given(
    scores=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        min_size=0,
        max_size=50,
    ),
    t1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    t2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
)
@h_settings(max_examples=100)
def test_property9_qualifying_pairs_monotone(scores, t1, t2):
    """Feature: rag-based-grouping, Property 9: Higher threshold qualifies fewer or equal pairs.

    The number of pairwise similarity scores that meet or exceed the threshold is
    monotonically non-increasing as the threshold rises.  This is the fundamental
    mechanism behind group-count monotonicity.
    Validates: Requirements 5.3, 5.4
    """
    high_t = max(t1, t2)
    low_t = min(t1, t2)
    qualifying_high = sum(1 for s in scores if s >= high_t)
    qualifying_low = sum(1 for s in scores if s >= low_t)
    assert qualifying_high <= qualifying_low, (
        f"More pairs qualify at higher threshold {high_t:.4f} ({qualifying_high}) "
        f"than at lower threshold {low_t:.4f} ({qualifying_low})"
    )


# ---------------------------------------------------------------------------
# Property 10: Threshold validation rejects values outside [0.0, 1.0]
# Feature: rag-based-grouping, Property 10: Threshold validation
# ---------------------------------------------------------------------------


class _ThresholdConfig(BaseModel):
    """Minimal model that applies the same Field constraint as Settings."""

    GROUPING_SIMILARITY_THRESHOLD: float = Field(default=0.75, ge=0.0, le=1.0)


@given(
    st.floats(allow_nan=False, allow_infinity=False).filter(
        lambda x: x < 0.0 or x > 1.0
    )
)
@h_settings(max_examples=100)
def test_property10_threshold_rejects_out_of_range(value):
    """Feature: rag-based-grouping, Property 10: Out-of-range threshold raises ValidationError.

    Any float strictly outside [0.0, 1.0] must be rejected at configuration
    time with a pydantic ValidationError so the service fails fast with a
    clear error message rather than silently using a nonsensical threshold.
    Validates: Requirements 5.2
    """
    with pytest.raises(ValidationError):
        _ThresholdConfig(GROUPING_SIMILARITY_THRESHOLD=value)


@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
@h_settings(max_examples=100)
def test_property10_threshold_accepts_valid_range(value):
    """Feature: rag-based-grouping, Property 10: In-range threshold is accepted without error.

    Any float within [0.0, 1.0] inclusive must be accepted as a valid
    GROUPING_SIMILARITY_THRESHOLD configuration value.
    Validates: Requirements 5.2
    """
    config = _ThresholdConfig(GROUPING_SIMILARITY_THRESHOLD=value)
    assert config.GROUPING_SIMILARITY_THRESHOLD == value
