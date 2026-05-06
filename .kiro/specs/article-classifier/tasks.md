# Implementation Plan: Article Classifier

## Overview

Build a FastAPI microservice that classifies articles using LLM (LangGraph/LangChain + OpenRouter). The service reads unprocessed articles from the shared PostgreSQL database, processes them through a single structured LLM call, validates and persists results, and exposes a REST API for querying. Implementation follows existing rag-agent and rss-feed patterns.

## Tasks

- [x] 1. Set up project structure and configuration
  - [x] 1.1 Create project skeleton with pyproject.toml, .gitignore, .dockerignore
    - Create `article-classifier/` directory with `pyproject.toml` (hatchling build, dependencies: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, langchain-openai, langgraph, langsmith, pydantic-settings, structlog, alembic; dev: pytest, pytest-asyncio, hypothesis, respx, httpx)
    - Create `.gitignore` and `.dockerignore` following rag-agent patterns
    - _Requirements: 10.1_

  - [x] 1.2 Implement config.py with pydantic-settings
    - Create `src/__init__.py` and `src/config.py` with Settings class
    - Required: DATABASE_URL, OPENROUTER_API_KEY
    - Optional with defaults: APP_PORT (8002), LLM_MODEL ("openai/gpt-4o-mini"), BATCH_SIZE (20), LLM_RETRY_DELAY_SECONDS (5), LLM_MAX_RETRIES (3), LANGSMITH_API_KEY, LANGSMITH_PROJECT ("sinalo-classifier"), LANGSMITH_TRACING ("true")
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 1.3 Create .env.example with all environment variables documented
    - Include all required and optional variables with placeholder values and comments
    - _Requirements: 10.4_

  - [x] 1.4 Create constants.py with TAG_TAXONOMY and ContentType enum
    - Define `TAG_TAXONOMY` dict with 7 main categories and their subcategories (categories are fixed, subcategories are dynamically expandable)
    - Define `ContentType` string enum with 7 values
    - _Requirements: 2.3, 3.1_

- [x] 2. Implement database layer
  - [x] 2.1 Create database.py with async SQLAlchemy engine and session factory
    - Async engine with asyncpg, session factory, SSL handling
    - Follow rag-agent/rss-feed database patterns
    - _Requirements: 1.1_

  - [x] 2.2 Create models.py with SQLAlchemy ORM models
    - Tag model: id, name (String 50), parent_id (self-referencing FK, nullable), created_at; UNIQUE(parent_id, name)
    - ClassificationResult model: id, article_id (FK articles.id, UNIQUE), content_type, importance_score (CHECK 0-10), summary, reason, llm_model, token_usage, processing_time_ms, classified_at
    - ArticleTag model: id, classification_result_id (FK), tag_id (FK), created_at; UNIQUE(classification_result_id, tag_id)
    - _Requirements: 2.4, 8.4, 8.7_

  - [x] 2.3 Create Alembic migration for initial schema
    - Set up alembic.ini and alembic/env.py
    - Create migration `001_initial.py` that creates tags, classification_results, and article_tags tables
    - _Requirements: 2.4_

- [x] 3. Implement classification pipeline
  - [x] 3.1 Create schemas.py with Pydantic models
    - LLMClassificationResponse: tags (list of TagOutput), content_type (str), score (int), reason (str), summary (str)
    - TagOutput: category (str), subcategory (str)
    - API response schemas: ClassifiedArticleResponse, PaginatedResponse, ClassifyTriggerResponse, ClassifyStatusResponse, HealthResponse
    - _Requirements: 8.2, 6.11_

  - [x] 3.2 Implement pipeline.py with LangGraph classification pipeline
    - Create ClassificationPipeline class using ChatOpenAI with OpenRouter base_url
    - Build LLM prompt in English that includes: article title, text, summary, full existing tag list, ContentType enum values, scoring criteria (Czech-focused), instruction for Czech summary output
    - Single LLM call returning structured JSON with all classification fields
    - Implement retry logic for HTTP 429 (configurable delay and max retries)
    - Handle non-retryable errors by raising appropriate exceptions
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6, 2.2, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4_

  - [x]* 3.3 Write property test for content type validation (Property 3)
    - **Property 3: Content type validation with fallback**
    - For any string value, validation returns the same value if it matches ContentType enum, or GENERAL_VALUABLE_CONTENT otherwise
    - **Validates: Requirements 3.1, 3.3**

  - [x]* 3.4 Write property test for score clamping (Property 4)
    - **Property 4: Score clamping**
    - For any integer value, clamping returns max(0, min(10, value))
    - **Validates: Requirements 4.1, 4.5**

  - [x]* 3.5 Write property test for short text bypass (Property 5)
    - **Property 5: Short text bypass**
    - For any article with extracted_text < 100 characters, the text is used directly as summary without LLM
    - **Validates: Requirements 5.5**

- [x] 4. Implement classifier service with tag validation
  - [x] 4.1 Implement classifier_service.py — article fetching and batch orchestration
    - `get_unprocessed_articles()`: query articles with non-null, non-empty extracted_text and no classification_results record
    - `classify_batch()`: process one batch of articles through the pipeline
    - `run_classification()`: process all unprocessed articles in configurable batch sizes with in-memory lock to prevent concurrent runs
    - Implement tag validation: match existing tags, run LLM dedup check for unknown tags, create genuinely new tags, enforce 1-5 tags per article
    - Persist classification results with all fields (including llm_model, token_usage, processing_time_ms)
    - Handle failed articles: log error, mark as failed, continue to next
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.5, 2.6, 2.7, 2.8, 8.4, 8.6, 8.7_

  - [x]* 4.2 Write property test for unprocessed article selection (Property 1)
    - **Property 1: Unprocessed article selection**
    - For any set of articles with varying extracted_text states and classification results, fetch returns exactly those with non-null, non-empty extracted_text and no classification result
    - **Validates: Requirements 1.1, 1.3**

  - [x]* 4.3 Write property test for tag validation and deduplication (Property 2)
    - **Property 2: Tag validation and deduplication**
    - For any list of tag objects, validation maps known tags directly, runs dedup for unknown, and ensures 1-5 final tags
    - **Validates: Requirements 2.2, 2.5, 2.6, 2.7, 2.8**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement REST API routes
  - [x] 6.1 Implement routes.py — GET /api/articles with filtering, sorting, pagination
    - Query parameters: category, subcategory, content_type, min_score, date_from, date_to, sort_by (default: classified_at), sort_order (default: desc), page (default: 1), size (default: 20, max: 100)
    - AND logic for combined filters
    - Response includes: article id, title, url, author, published_at, tags, content_type, importance_score, summary, classified_at
    - Paginated response with total count and pages
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11_

  - [x] 6.2 Implement routes.py — POST /api/classify and GET /api/classify/status
    - POST /api/classify: trigger async classification, return 202 with queued count, reject with 409 if already running
    - GET /api/classify/status: return current state (idle/processing, pending count, classified count)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 6.3 Implement routes.py — GET /health endpoint
    - Check database connectivity, return 200 with status "ok" or 503 with "unavailable"
    - _Requirements: 9.1, 9.5_

  - [x]* 6.4 Write property test for API filtering correctness (Property 6)
    - **Property 6: API filtering correctness**
    - For any set of classified articles and filter combinations, every returned article satisfies ALL applied filters (AND logic)
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6, 6.10**

  - [x]* 6.5 Write property test for API sorting correctness (Property 7)
    - **Property 7: API sorting correctness**
    - For any valid sort_by field and sort_order, returned articles are ordered correctly
    - **Validates: Requirements 6.7, 6.8**

  - [x]* 6.6 Write property test for API pagination correctness (Property 8)
    - **Property 8: API pagination correctness**
    - For any valid pagination params, response contains at most `size` items, total equals full count, pages equals ceil(total/size)
    - **Validates: Requirements 6.9**

- [x] 7. Implement main.py with FastAPI app and lifespan
  - Create FastAPI app with lifespan handler
  - Configure structlog with JSON output
  - Configure LangSmith tracing in lifespan
  - Create database tables on startup
  - Seed initial tag taxonomy from TAG_TAXONOMY constants on startup
  - Register routes, global exception handler (500 with error type and message)
  - _Requirements: 9.2, 9.3, 9.4, 2.3_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Create infrastructure and deployment files
  - [ ] 9.1 Create Dockerfile with multi-stage build
    - Builder stage: python:3.12-slim, install hatchling, copy pyproject.toml, install deps to /app/deps, copy src
    - Production stage: python:3.12-slim, copy deps and src, set PYTHONPATH, expose 8002
    - Follow rag-agent Dockerfile pattern
    - _Requirements: 10.1_

  - [ ] 9.2 Create fly.toml for Fly.io deployment
    - App name: "sinalo-classifier", region: "fra"
    - [env] section with non-sensitive config: APP_PORT, LLM_MODEL, BATCH_SIZE, LANGSMITH_PROJECT, LANGSMITH_TRACING, LLM_RETRY_DELAY_SECONDS, LLM_MAX_RETRIES
    - HTTP service on internal port 8002, auto_stop/auto_start machines
    - VM: 512mb shared CPU
    - _Requirements: 10.3_

  - [ ] 9.3 Create scripts/start-docker.sh
    - Parse APP_NAME from fly.toml
    - Build Docker image, stop/remove existing container, run with --env-file .env
    - Expose port 8002
    - _Requirements: 10.1_

  - [ ] 9.4 Create scripts/fly-setup.sh
    - Parse APP_NAME from fly.toml
    - Create Fly.io app if needed
    - Set secrets from .env, skipping keys in fly.toml [env]
    - Follow rag-agent/scripts/fly-setup.sh pattern
    - _Requirements: 10.1_

  - [ ] 9.5 Create scripts/classifier.sh CLI script
    - Commands: classify, status, articles (with filter flags), health, help
    - Filter flags: --category, --subcategory, --type, --min-score, --from, --to, --sort, --order, --page, --size, --json
    - Environment: CLASSIFIER_API_URL (default http://localhost:8002)
    - Follow feed-parser.sh pattern (POSIX sh, .env loading, curl+jq)
    - _Requirements: 7.1, 7.4, 6.1, 9.1_

- [ ] 10. Update deploy.sh and create README.md
  - [ ] 10.1 Update root deploy.sh to include article-classifier service
    - Add `deploy_classifier()` function deploying article-classifier to Fly.io
    - Add `setup_classifier()` function running fly-setup.sh
    - Add `run_migrations_classifier()` function running alembic upgrade head via fly ssh
    - Add "classifier" option to case statement
    - Update "setup" and "all" options to include classifier
    - Update usage text

  - [ ] 10.2 Create README.md with setup and deployment instructions
    - Local Docker setup (copy .env.example, start-docker.sh, connects to remote PostgreSQL)
    - Fly.io deployment (fly-setup.sh, fly deploy)
    - CLI usage examples
    - _Requirements: 10.4_

- [ ] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The service shares PostgreSQL with rss-feed (reads articles table, writes own tables)
- All LLM prompts must be in English; summary output language is controlled via prompt instruction
- Follow existing rag-agent and rss-feed patterns for consistency
