# Implementation Plan: RAG-Based Grouping

## Overview

Replace LLM-based article clustering with vector similarity-based grouping using Qdrant. The implementation proceeds from foundational configuration through data layer changes, new service components, rewriting the grouping logic, simplifying the pipeline, updating routes, and finally testing and documentation.

## Tasks

- [x] 1. Configuration and dependencies
  - [x] 1.1 Add Qdrant, embedding, and threshold settings to `article-classifier/src/config.py`
    - Add `QDRANT_URL` (default: `http://localhost:6333`), `QDRANT_API_KEY` (optional), `QDRANT_FULL_ARTICLE_COLLECTION` (default: `article_full`)
    - Add `EMBEDDING_MODEL` (default: `openai/text-embedding-3-small`), `EMBEDDING_API_URL` (default: `https://openrouter.ai/api/v1`)
    - Add `GROUPING_SIMILARITY_THRESHOLD` with `Field(ge=0.0, le=1.0)` validation (default: 0.75)
    - Remove `GROUPING_VALIDATE_CLUSTERS` setting (no longer needed)
    - _Requirements: 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 1.2 Add `qdrant-client` and `httpx` to project dependencies via `uv`
    - Run `uv add qdrant-client httpx` in the `article-classifier/` directory
    - Verify `httpx` is not already present (it may be a transitive dependency)
    - _Requirements: 1.1, 2.2_

- [x] 2. Database migration and model updates
  - [x] 2.1 Add `needs_regeneration` column to `ArticleGroup` model in `article-classifier/src/models.py`
    - Add `needs_regeneration: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)`
    - Import `Boolean` from sqlalchemy
    - _Requirements: 3.10, 4.6_

  - [x] 2.2 Add `FullArticleIndexed` model to `article-classifier/src/models.py`
    - Create model with `article_id` (PK, FK to articles with CASCADE delete) and `indexed_at` (DateTime, default now)
    - _Requirements: 2.4_

  - [x] 2.3 Create SQL migration script at `article-classifier/scripts/migration_rag_grouping.sql`
    - Add `needs_regeneration BOOLEAN NOT NULL DEFAULT false` to `article_groups`
    - Create `full_article_indexed` table with `article_id` (PK, FK) and `indexed_at`
    - _Requirements: 2.4, 3.10_

- [x] 3. Checkpoint - Ensure models are correct
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. EmbeddingClient
  - [ ] 4.1 Create `article-classifier/src/embedding_client.py`
    - Reuse pattern from `rag-agent/src/embeddings.py`
    - Implement `EmbeddingError` exception class
    - Implement `EmbeddingClient` with `__init__(api_url, api_key, model)`
    - Implement `embed_text(text: str) -> list[float]` for single text embedding
    - Implement `embed_texts(texts: list[str]) -> list[list[float]]` for batch embedding
    - Use `httpx.AsyncClient` with 60s timeout, Bearer auth, sorted response by index
    - _Requirements: 2.2, 2.5_

  - [ ]* 4.2 Write unit tests for EmbeddingClient in `article-classifier/tests/test_embedding_client.py`
    - Mock httpx responses, verify correct API call format
    - Test error handling (HTTP errors, request errors)
    - Test empty input returns empty list
    - _Requirements: 2.2, 2.5_

- [ ] 5. SimilarityService
  - [ ] 5.1 Create `article-classifier/src/similarity_service.py`
    - Implement `SimilarityService` with `__init__(qdrant_client, settings)`
    - Implement `ensure_collection(vector_size=1536)` — create collection if not exists with cosine distance
    - Implement `upsert_article(article_id, vector, metadata)` — upsert single point with deterministic UUID5 ID
    - Implement `find_most_similar(article_id, vector, exclude_ids=None) -> tuple[int, float] | None` — query for top-1 match excluding self
    - Implement static `make_point_id(article_id) -> str` using `uuid.uuid5` with fixed namespace
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2_

  - [ ]* 5.2 Write unit tests for SimilarityService in `article-classifier/tests/test_similarity_service.py`
    - Mock Qdrant client, verify upsert/query calls
    - Test deterministic point ID generation
    - Test self-exclusion filter in find_most_similar
    - Test None return when no results
    - _Requirements: 1.5, 3.2_

- [ ] 6. Rewrite GroupingService
  - [ ] 6.1 Rewrite `article-classifier/src/grouping_service.py` to use vector similarity
    - Replace LLM clustering with: fetch candidates → embed → upsert → similarity search → group decisions
    - Add `EmbeddingClient` and `SimilarityService` as dependencies
    - Retain `GroupingPipeline` reference only for `generate_detail()` (used in regeneration)
    - Implement candidate selection: classified articles not in `full_article_indexed` table for target date
    - Implement sequential processing: for each candidate, embed text, upsert to Qdrant, find most similar, apply threshold logic
    - Implement group creation: if match above threshold and match is ungrouped, create new group with placeholder title (first member's title), empty summary/detail, `needs_regeneration=True`
    - Implement group joining: if match above threshold and match is in existing group, add to group, update `grouped_date` to most recent member's `published_at`, set `needs_regeneration=True`
    - Implement standalone: if below threshold, leave article ungrouped
    - Track indexed articles in `full_article_indexed` table after successful upsert
    - Skip articles with empty `extracted_text`
    - Handle embedding errors gracefully (skip article, continue)
    - Handle Qdrant errors gracefully (log, skip or abort as appropriate)
    - Respect existing unique constraint on `article_group_members.article_id`
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 7.4, 7.5, 7.6, 9.1_

  - [ ] 6.2 Implement `run_regeneration()` method in `GroupingService`
    - Fetch all groups where `needs_regeneration = True`
    - For each group, load member articles with `extracted_text`
    - Call `GroupingPipeline.generate_detail()` with member articles
    - Update group title, summary, detail from LLM response
    - Clear `needs_regeneration` flag on success
    - On failure, log error and leave flag set for retry
    - Return `RegenerationResponse` with count of groups regenerated
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [ ]* 6.3 Write unit tests for GroupingService in `article-classifier/tests/test_grouping_service.py`
    - Test candidate selection (only classified, unindexed articles)
    - Test sequential processing (article C joins group created by A+B)
    - Test threshold logic (above → group, below → standalone)
    - Test error handling (embedding failure skips article)
    - Test regeneration processes only flagged groups
    - _Requirements: 2.1, 3.4, 3.5, 3.6, 4.1, 4.6_

- [ ] 7. Simplify GroupingPipeline
  - [ ] 7.1 Remove clustering and validation methods from `article-classifier/src/grouping_pipeline.py`
    - Remove `cluster()` method and `_cluster_node`
    - Remove `validate_cluster()` method
    - Remove `_ClusteringState` type
    - Remove `_CLUSTERING_SYSTEM_PROMPT` and `_build_clustering_prompt()`
    - Remove `_clustering_llm`, `_validation_llm`, `_clustering_graph`
    - Remove `_build_clustering_graph()` method
    - Keep `generate_detail()` method, `_detail_node`, `_DetailState`, `_DETAIL_SYSTEM_PROMPT`, `_build_detail_prompt()`
    - Keep `_build_detail_graph()` and `_detail_graph`
    - Keep `_call_with_retry()` helper (used by detail generation)
    - _Requirements: 9.3, 9.4_

- [ ] 8. Checkpoint - Ensure core logic is correct
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Routes and schemas
  - [ ] 9.1 Add `RegenerationResponse` schema to `article-classifier/src/grouping_schemas.py`
    - Add `RegenerationResponse(BaseModel)` with `groups_regenerated: int`
    - _Requirements: 4.1, 4.8_

  - [ ] 9.2 Add `POST /api/groups/regenerate` endpoint to `article-classifier/src/routes.py`
    - Call `GroupingService.run_regeneration()`
    - Return `RegenerationResponse`
    - _Requirements: 4.1, 4.8_

  - [ ] 9.3 Update `POST /api/groups/generate` endpoint to use new grouping logic
    - Verify it calls the rewritten `GroupingService.run_grouping()` (should work without changes since the method signature is preserved)
    - Ensure the endpoint does NOT trigger detail generation (only similarity matching)
    - _Requirements: 7.1, 7.4, 7.6_

  - [ ] 9.4 Add `regenerate` command to `article-classifier/scripts/classifier.sh`
    - Add `cmd_regenerate` function that calls `POST /api/groups/regenerate`
    - Display `groups_regenerated` count in formatted output
    - Add `--json` flag support
    - Add help text for the new command
    - Add `regenerate` to the dispatch case and usage_main
    - _Requirements: 4.1, 4.8_

- [ ] 10. Property-based tests
  - [ ]* 10.1 Write property test for indexing determinism and completeness
    - **Property 1: Indexing produces exactly one point per article with deterministic ID and complete metadata**
    - **Validates: Requirements 1.3, 1.4, 1.5**

  - [ ]* 10.2 Write property test for candidate selection
    - **Property 2: Only classified, unindexed articles are selected as candidates**
    - **Validates: Requirements 2.1, 2.4**

  - [ ]* 10.3 Write property test for self-exclusion
    - **Property 3: Self-exclusion from similarity search**
    - **Validates: Requirements 3.2**

  - [ ]* 10.4 Write property test for grouping decision correctness
    - **Property 4: Grouping decision correctness based on threshold and group membership**
    - **Validates: Requirements 3.4, 3.5, 3.6**

  - [ ]* 10.5 Write property test for single-group membership
    - **Property 5: Single-group membership invariant**
    - **Validates: Requirements 3.8**

  - [ ]* 10.6 Write property test for grouped_date correctness
    - **Property 6: grouped_date reflects most recent member**
    - **Validates: Requirements 3.9**

  - [ ]* 10.7 Write property test for needs_regeneration on modification
    - **Property 7: needs_regeneration is set on group creation or modification**
    - **Validates: Requirements 3.10**

  - [ ]* 10.8 Write property test for needs_regeneration cleared after regeneration
    - **Property 8: needs_regeneration is cleared after successful detail regeneration**
    - **Validates: Requirements 4.6**

  - [ ]* 10.9 Write property test for threshold monotonicity
    - **Property 9: Threshold monotonicity — higher threshold produces fewer or equal groups**
    - **Validates: Requirements 5.3, 5.4**

  - [ ]* 10.10 Write property test for threshold validation
    - **Property 10: Threshold validation rejects values outside [0.0, 1.0]**
    - **Validates: Requirements 5.2**

- [ ] 11. Environment files and documentation
  - [ ] 11.1 Update `article-classifier/.env.example` with new environment variables
    - Add `QDRANT_URL=http://localhost:6333`
    - Add `QDRANT_API_KEY=your-qdrant-api-key` (optional)
    - Add `QDRANT_FULL_ARTICLE_COLLECTION=article_full`
    - Add `EMBEDDING_MODEL=openai/text-embedding-3-small`
    - Add `EMBEDDING_API_URL=https://openrouter.ai/api/v1`
    - Add `GROUPING_SIMILARITY_THRESHOLD=0.75`
    - Remove `GROUPING_VALIDATE_CLUSTERS` entry
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 11.2 Update `article-classifier/.env` with new environment variables
    - Add same variables as `.env.example` with appropriate values for the development environment
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ] 11.3 Update project README with new grouping approach documentation
    - Describe RAG-based similarity grouping approach (embed → query → threshold → group)
    - Document new configuration variables
    - Document the two-step workflow: `POST /api/groups/generate` for similarity matching, `POST /api/groups/regenerate` for detail generation
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The EmbeddingClient pattern is copied from `rag-agent/src/embeddings.py` with minor adaptations
- The existing `GroupingPipeline.generate_detail()` is retained unchanged for the regeneration flow
- All property-based tests should be placed in `article-classifier/tests/test_grouping_properties.py` using Hypothesis with `@settings(max_examples=100)`
