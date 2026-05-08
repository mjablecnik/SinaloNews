"""Property tests for grouping pipeline validation logic.

Feature: article-grouping
"""

from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from src.grouping_schemas import (
    ClusterItem,
    ClusteringOutput,
    ExistingGroupAddition,
)


# ---------------------------------------------------------------------------
# Pure helper that mirrors GroupingService._validate_clustering_output
# ---------------------------------------------------------------------------


def _validate_clustering_output(
    output: ClusteringOutput,
    valid_article_ids: set[int],
) -> ClusteringOutput:
    """Mirrors GroupingService._validate_clustering_output without DB/logging."""
    seen: set[int] = set()
    valid_groups: list[ClusterItem] = []

    for cluster in output.groups:
        local_seen: set[int] = set()
        filtered_ids = []
        for aid in cluster.article_ids:
            if aid in valid_article_ids and aid not in seen and aid not in local_seen:
                filtered_ids.append(aid)
                local_seen.add(aid)
        if len(filtered_ids) < 2:
            continue
        seen.update(filtered_ids)
        valid_groups.append(ClusterItem(
            article_ids=filtered_ids,
            topic=cluster.topic,
            justification=cluster.justification,
        ))

    valid_additions: list[ExistingGroupAddition] = []
    for addition in output.existing_group_additions:
        local_seen: set[int] = set()
        filtered_ids = []
        for aid in addition.article_ids:
            if aid in valid_article_ids and aid not in seen and aid not in local_seen:
                filtered_ids.append(aid)
                local_seen.add(aid)
        if not filtered_ids:
            continue
        seen.update(filtered_ids)
        valid_additions.append(ExistingGroupAddition(
            group_id=addition.group_id,
            article_ids=filtered_ids,
        ))

    return ClusteringOutput(
        groups=valid_groups,
        existing_group_additions=valid_additions,
        standalone_ids=output.standalone_ids,
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_article_id_strategy = st.integers(min_value=1, max_value=50)

_cluster_item_strategy = st.builds(
    ClusterItem,
    article_ids=st.lists(_article_id_strategy, min_size=0, max_size=6),
    topic=st.text(min_size=1, max_size=50),
    justification=st.text(min_size=1, max_size=100),
)

_existing_group_addition_strategy = st.builds(
    ExistingGroupAddition,
    group_id=st.integers(min_value=1, max_value=20),
    article_ids=st.lists(_article_id_strategy, min_size=0, max_size=5),
)

_clustering_output_strategy = st.builds(
    ClusteringOutput,
    groups=st.lists(_cluster_item_strategy, min_size=0, max_size=8),
    existing_group_additions=st.lists(_existing_group_addition_strategy, min_size=0, max_size=5),
    standalone_ids=st.lists(_article_id_strategy, min_size=0, max_size=10),
)

_valid_ids_strategy = st.frozensets(
    _article_id_strategy, min_size=0, max_size=50
).map(set)


# ---------------------------------------------------------------------------
# Feature: article-grouping, Property 4: Clustering output validation
# ---------------------------------------------------------------------------


@given(_clustering_output_strategy, _valid_ids_strategy)
@h_settings(max_examples=100)
def test_validation_discards_single_article_groups(output, valid_ids):
    """Property 4 (single-article discard): no validated group has fewer than 2 articles.

    After validation, every group in the result must contain at least 2 article IDs.
    Groups that end up with 0 or 1 valid/unseen articles must be discarded entirely.

    Validates: Requirements 2.8
    """
    result = _validate_clustering_output(output, valid_ids)
    for group in result.groups:
        assert len(group.article_ids) >= 2, (
            f"Validated group has only {len(group.article_ids)} articles "
            f"(topic='{group.topic}') — must be >= 2"
        )


@given(_clustering_output_strategy, _valid_ids_strategy)
@h_settings(max_examples=100)
def test_validation_no_article_in_multiple_groups(output, valid_ids):
    """Property 4 (deduplication): no article ID appears in more than one output group.

    After validation, each article ID must appear in at most one output group,
    counting both new groups and existing_group_additions.

    Validates: Requirements 2.9
    """
    result = _validate_clustering_output(output, valid_ids)
    seen: set[int] = set()
    for group in result.groups:
        for aid in group.article_ids:
            assert aid not in seen, (
                f"Article ID {aid} appears in more than one validated group"
            )
            seen.add(aid)
    for addition in result.existing_group_additions:
        for aid in addition.article_ids:
            assert aid not in seen, (
                f"Article ID {aid} appears in both a new group and an existing_group_addition"
            )
            seen.add(aid)


@given(_clustering_output_strategy, _valid_ids_strategy)
@h_settings(max_examples=100)
def test_validation_only_valid_ids_survive(output, valid_ids):
    """Property 4 (soundness): only IDs from valid_article_ids appear in the output.

    After validation, every article ID in every output group must be contained
    in valid_article_ids.

    Validates: Requirements 2.8, 2.9
    """
    result = _validate_clustering_output(output, valid_ids)
    for group in result.groups:
        for aid in group.article_ids:
            assert aid in valid_ids, (
                f"Article ID {aid} in validated group is not in valid_article_ids"
            )
    for addition in result.existing_group_additions:
        for aid in addition.article_ids:
            assert aid in valid_ids, (
                f"Article ID {aid} in existing_group_addition is not in valid_article_ids"
            )
