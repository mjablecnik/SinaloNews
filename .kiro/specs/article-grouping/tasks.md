# Implementation Plan: Article Grouping

## Overview

This plan implements the article grouping feature as a post-classification pipeline that clusters similar articles by topic within a day and category, generates consolidated AI summaries, and exposes them through a mixed feed API. The backend (Python/FastAPI) gets new database models, a grouping pipeline, service layer, and API endpoints. The frontend (SvelteKit) gets new types, API functions, a GroupCard component, feed integration, and a group detail page.

## Tasks

- [x] 1. Database models and migration
  - [x] 1.1 Add ArticleGroup and ArticleGroupMember SQLAlchemy models to `article-classifier/src/models.py`
    - Add `ArticleGroup` model with columns: id, title, summary, detail, category, grouped_date, llm_model, token_usage, created_at, updated_at
    - Add composite index on `(category, grouped_date)`
    - Add `ArticleGroupMember` model with columns: id, group_id (FK), article_id (FK, UNIQUE), created_at
    - Add relationships: ArticleGroup.members, ArticleGroupMember.group, ArticleGroupMember.article
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 1.2 Create Alembic migration `article-classifier/alembic/versions/002_article_groups.py`
    - Create `article_groups` table with all columns and composite index
    - Create `article_group_members` table with foreign keys and unique constraint on article_id
    - Add ON DELETE CASCADE for group_id foreign key
    - _Requirements: 4.1, 4.2, 4.3_

- [x] 2. Configuration extensions
  - [x] 2.1 Add grouping settings to `article-classifier/src/config.py`
    - Add `GROUPING_LLM_MODEL: str | None = None` (falls back to LLM_MODEL)
    - Add `GROUPING_MIN_ARTICLES: int = 2`
    - Add `GROUPING_MAX_ARTICLES_PER_CATEGORY: int = 50`
    - Update `.env.example` with new optional variables
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [x] 3. Grouping pipeline (LLM calls)
  - [x] 3.1 Create Pydantic schemas in `article-classifier/src/grouping_schemas.py`
    - Define `ArticleForClustering` (id, title, summary, source_url)
    - Define `ExistingGroupForClustering` (group_id, title, summary)
    - Define `ClusterItem`, `ExistingGroupAddition`, `ClusteringLLMResponse` for structured output
    - Define `ArticleForDetail` (id, title, extracted_text)
    - Define `GroupDetailLLMResponse` (title, summary, detail)
    - Define `ClusteringOutput` (groups, existing_group_additions, standalone_ids)
    - Define `GroupDetailOutput` (title, summary, detail)
    - Define API response schemas: `GroupSummaryResponse`, `GroupDetailResponse`, `GroupMemberResponse`, `FeedItem`, `FeedResponse`, `GroupingTriggerResponse`
    - _Requirements: 10.4, 10.5, 6.5, 6.7, 7.6, 7.7_

  - [x] 3.2 Implement grouping pipeline in `article-classifier/src/grouping_pipeline.py`
    - Create `GroupingPipeline` class with LangGraph state graph
    - Implement `cluster()` method: builds English prompt with article titles/summaries and existing groups, uses structured output to get `ClusteringLLMResponse`
    - Implement `generate_detail()` method: builds English prompt with full extracted_text of member articles, instructs output in Czech, uses structured output to get `GroupDetailLLMResponse`
    - Implement retry logic (same pattern as ClassificationPipeline._call_with_retry)
    - Use `GROUPING_LLM_MODEL` if set, otherwise fall back to `LLM_MODEL`
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 10.1, 10.2, 10.5, 10.6_

- [ ] 4. Grouping service (orchestration)
  - [x] 4.1 Implement grouping service in `article-classifier/src/grouping_service.py`
    - Create `GroupingService` class
    - Implement `get_candidates(session, target_date)`: query articles with classification result + summary, not in article_group_members, published_at on target_date, grouped by first tag category
    - Implement `get_existing_groups(session, target_date)`: fetch existing groups for the date, grouped by category
    - Implement `_validate_clustering_output()`: discard single-article groups, deduplicate article assignments across groups
    - Implement `run_grouping(target_date)`: orchestrate full flow — get candidates, partition by category, enforce max articles limit (most recent), skip categories below threshold, call pipeline.cluster(), validate output, persist new groups, handle existing group additions with detail regeneration
    - Use per-category transaction rollback on failure
    - Record llm_model and token_usage on each ArticleGroup
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.4, 2.8, 2.9, 4.6, 4.7, 5.4, 5.5, 10.3, 10.7, 11.3, 11.4, 11.5_

  - [x]* 4.2 Write property test: Candidate selection correctness (Property 1)
    - **Property 1: Candidate selection correctness**
    - Generate random article sets with varying dates, classification states, summary presence, and group memberships
    - Assert candidate selection returns exactly articles matching all three conditions
    - **Validates: Requirements 1.1, 1.4**

  - [x]* 4.3 Write property test: Category partitioning correctness (Property 2)
    - **Property 2: Category partitioning correctness**
    - Generate random articles with varying tag assignments
    - Assert partitioning produces correct category buckets with no article in multiple categories
    - **Validates: Requirements 1.2, 1.3**

  - [x]* 4.4 Write property test: Minimum articles threshold (Property 3)
    - **Property 3: Minimum articles threshold**
    - Generate random category partitions with varying sizes and threshold values
    - Assert clustering is only invoked for categories meeting the threshold
    - **Validates: Requirements 1.5**

  - [ ]* 4.5 Write property test: Clustering output validation (Property 4)
    - **Property 4: Clustering output validation**
    - Generate random clustering LLM responses with edge cases (single-article groups, duplicate IDs)
    - Assert validation discards single-article groups and deduplicates assignments
    - **Validates: Requirements 2.8, 2.9**

  - [ ]* 4.6 Write property test: Max articles per category truncation (Property 9)
    - **Property 9: Max articles per category truncation**
    - Generate random candidate lists of varying sizes with a max limit
    - Assert only the most recent articles up to the limit are passed to clustering
    - **Validates: Requirements 11.5**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. API endpoints (groups + feed)
  - [x] 6.1 Add group and feed endpoints to `article-classifier/src/routes.py`
    - `POST /api/groups/generate` — trigger grouping for a date (default: today), return stats
    - `GET /api/groups` — list groups with filters: category, date, date_from, date_to, page, size
    - `GET /api/groups/{id}` — group detail with member articles
    - `GET /api/feed` — mixed feed of groups + standalone articles with filters: category, subcategory, date_from, date_to, min_score, page, size
    - Feed excludes articles that belong to any group
    - Feed sorts by date ascending (published_at for articles, grouped_date for groups)
    - Group importance_score computed as max of member scores; group tags as union of member tags
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12_

  - [ ]* 6.2 Write property test: Group list filtering and pagination (Property 5)
    - **Property 5: Group list filtering and pagination**
    - Generate random groups with varying attributes and filter/pagination params
    - Assert correct filtering, page size limits, total count, and pages calculation
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.9**

  - [ ]* 6.3 Write property test: Feed exclusion invariant (Property 6)
    - **Property 6: Feed exclusion invariant**
    - Generate random articles with some grouped and some standalone
    - Assert feed never returns grouped articles as standalone items
    - **Validates: Requirements 7.1, 7.8**

  - [ ]* 6.4 Write property test: Feed filtering correctness (Property 7)
    - **Property 7: Feed filtering correctness**
    - Generate random mixed feed data with varying filter params
    - Assert standalone articles satisfy all filters directly; groups satisfy category/date filters on own fields, min_score via max member score, subcategory if any member matches
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.11, 7.12**

  - [ ]* 6.5 Write property test: Feed sorting and pagination (Property 8)
    - **Property 8: Feed sorting and pagination**
    - Generate random mixed feed data
    - Assert items sorted by date ascending and pagination returns correct counts
    - **Validates: Requirements 7.9, 7.10**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. CLI script extension
  - [x] 8.1 Add grouping commands to `article-classifier/scripts/classifier.sh`
    - Add `group` command: POST /api/groups/generate (default today, --date=YYYY-MM-DD option)
    - Add `groups` command: GET /api/groups (--category option, --date option, --json flag)
    - Add `group-detail <id>` command: GET /api/groups/{id} (formatted output with member list)
    - Update usage_main and add usage_cmd entries for new commands
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

- [ ] 9. Frontend types and API functions
  - [x] 9.1 Add grouping types to `article-reader/src/lib/types.ts`
    - Add `FeedItem` interface with type discriminator ('article' | 'group')
    - Add `GroupDetail` interface with full group fields and members array
    - Add `GroupMemberArticle` interface
    - Add `FeedResponse` interface (paginated)
    - _Requirements: 7.6, 7.7, 8.1, 9.1_

  - [x] 9.2 Add feed and group API functions to `article-reader/src/lib/api.ts`
    - Add `getFeed(params)` function calling GET /api/feed with filter params
    - Add `getGroupDetail(id)` function calling GET /api/groups/{id}
    - _Requirements: 8.1, 9.1_

- [x] 10. Frontend GroupCard component
  - [x] 10.1 Create `article-reader/src/lib/components/GroupCard.svelte`
    - Display group title, short summary, member_count, grouped_date, importance_score
    - Visual indicator distinguishing it from ArticleCard (stacked card appearance or group icon)
    - Link to group detail page `/group/{id}`
    - Display tags (union of member tags)
    - _Requirements: 8.2, 8.3, 8.4, 8.5_

- [x] 11. Frontend feed integration
  - [x] 11.1 Update category page to use feed endpoint
    - Modify `article-reader/src/routes/category/[slug]/+page.ts` to call `getFeed` instead of `getArticles`
    - Modify `article-reader/src/routes/category/[slug]/+page.svelte` to render `GroupCard` for type="group" items and `ArticleCard` for type="article" items
    - Standalone articles continue using existing ArticleCard component
    - _Requirements: 8.1, 8.6_

- [x] 12. Frontend group detail page
  - [x] 12.1 Create group detail route `article-reader/src/routes/group/[id]/+page.ts`
    - Load group detail data via `getGroupDetail(id)`
    - _Requirements: 9.1_

  - [x] 12.2 Create group detail page `article-reader/src/routes/group/[id]/+page.svelte`
    - Display group title and full Group_Detail rendered as Markdown (reuse MarkdownRenderer component)
    - Display list of member articles with title, author, source domain, published_at
    - Each member article links to existing article detail page `/article/{id}` (internal navigation)
    - Do NOT link directly to original article URLs from this page
    - Provide navigation back to article list
    - Mark all member articles as read in ReadState
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (Hypothesis library)
- Unit tests validate specific examples and edge cases
- The backend uses Python (FastAPI, SQLAlchemy, LangGraph, Hypothesis)
- The frontend uses TypeScript (SvelteKit)
- All LLM prompts must be written in English with explicit Czech output language instructions
