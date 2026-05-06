"""Property tests for classifier service logic.

Feature: article-classifier
"""

from dataclasses import dataclass
from typing import Optional

from hypothesis import given
from hypothesis import strategies as st

from src.constants import TAG_TAXONOMY


# ---------------------------------------------------------------------------
# Pure helpers that mirror ClassifierService internals
# ---------------------------------------------------------------------------


def _is_unprocessed(extracted_text: Optional[str], has_classification: bool) -> bool:
    """Mirrors the WHERE clause in get_unprocessed_articles."""
    return (
        extracted_text is not None
        and extracted_text != ""
        and not has_classification
    )


@dataclass
class _FakeTag:
    id: int
    name: str
    parent_id: Optional[int]


@dataclass
class _FakeTagOut:
    category: str
    subcategory: str


def _validate_tags_pure(
    llm_tags: list[_FakeTagOut], existing_tags: list[_FakeTag]
) -> list[_FakeTag]:
    """Pure version of _validate_tags that maps known tags only (no LLM, no DB)."""
    parent_map = {t.name.lower(): t for t in existing_tags if t.parent_id is None}
    subcategory_map: dict[tuple[str, str], _FakeTag] = {}
    for t in existing_tags:
        if t.parent_id is not None:
            parent = next((p for p in existing_tags if p.id == t.parent_id), None)
            if parent:
                subcategory_map[(parent.name.lower(), t.name.lower())] = t

    validated: list[_FakeTag] = []
    seen: set[int] = set()
    for tag_out in llm_tags:
        cat_key = tag_out.category.lower()
        sub_key = tag_out.subcategory.lower()
        if cat_key not in parent_map:
            continue
        key = (cat_key, sub_key)
        if key in subcategory_map:
            tag = subcategory_map[key]
            if tag.id not in seen:
                validated.append(tag)
                seen.add(tag.id)
        if len(validated) == 5:
            break

    return validated


def _build_existing_tags() -> list[_FakeTag]:
    tags: list[_FakeTag] = []
    tag_id = 1
    for cat, subs in TAG_TAXONOMY.items():
        parent_id = tag_id
        tags.append(_FakeTag(id=tag_id, name=cat, parent_id=None))
        tag_id += 1
        for sub in subs:
            tags.append(_FakeTag(id=tag_id, name=sub, parent_id=parent_id))
            tag_id += 1
    return tags


_EXISTING_TAGS = _build_existing_tags()

_VALID_TAG_PAIRS = [
    (cat, sub)
    for cat, subs in TAG_TAXONOMY.items()
    for sub in subs
]


# ---------------------------------------------------------------------------
# Feature: article-classifier, Property 1: Unprocessed article selection
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.tuples(
            st.one_of(st.none(), st.text()),
            st.booleans(),
        ),
        max_size=30,
    )
)
def test_unprocessed_article_selection(articles):
    """Property 1: For any set of articles, the selection predicate returns True
    iff extracted_text is non-null and non-empty and no classification exists.
    Validates: Requirements 1.1, 1.3"""
    for extracted_text, has_classification in articles:
        result = _is_unprocessed(extracted_text, has_classification)
        expected = (
            extracted_text is not None
            and extracted_text != ""
            and not has_classification
        )
        assert result == expected


# ---------------------------------------------------------------------------
# Feature: article-classifier, Property 2: Tag validation and deduplication
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.sampled_from(_VALID_TAG_PAIRS).map(
            lambda p: _FakeTagOut(category=p[0], subcategory=p[1])
        ),
        min_size=0,
        max_size=10,
    )
)
def test_tag_validation_known_tags_mapped_directly(llm_tags):
    """Property 2 (known tags): known category+subcategory pairs are mapped
    directly and at most 5 are returned without duplicates.
    Validates: Requirements 2.2, 2.5, 2.6, 2.7, 2.8"""
    result = _validate_tags_pure(llm_tags, _EXISTING_TAGS)

    # Enforce max-5 limit
    assert len(result) <= 5

    # All returned tags exist in the seed set
    existing_ids = {t.id for t in _EXISTING_TAGS}
    for tag in result:
        assert tag.id in existing_ids

    # No duplicates
    result_ids = [t.id for t in result]
    assert len(result_ids) == len(set(result_ids))

    # Correct count: unique known pairs, capped at 5
    unique_keys: set[tuple[str, str]] = set()
    for tag_out in llm_tags:
        unique_keys.add((tag_out.category.lower(), tag_out.subcategory.lower()))
    assert len(result) == min(len(unique_keys), 5)


@given(
    st.lists(
        st.text(min_size=1).filter(
            lambda s: s.lower() not in {k.lower() for k in TAG_TAXONOMY}
        ),
        min_size=1,
        max_size=10,
    )
)
def test_tag_validation_invalid_categories_skipped(invalid_categories):
    """Property 2 (invalid categories): tags with unknown main categories are skipped.
    Validates: Requirements 2.6"""
    llm_tags = [_FakeTagOut(category=cat, subcategory="SomeSub") for cat in invalid_categories]
    result = _validate_tags_pure(llm_tags, _EXISTING_TAGS)
    assert result == [], "tags with unknown main categories must be skipped"
