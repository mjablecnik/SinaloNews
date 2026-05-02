# Implementation Plan: RSS Feed Pipeline

## Overview

Build a Python FastAPI service that discovers RSS/Atom feeds on registered websites, parses feed entries, downloads article HTML, and extracts text using Trafilatura. All operations are exposed as REST API endpoints backed by PostgreSQL. A bash CLI client wraps the API for terminal workflows. Implementation proceeds bottom-up: project setup → data layer → services → routes → CLI → infrastructure.

## Tasks

- [x] 1. Set up project structure, configuration, and database foundation
  - [x] 1.1 Create project skeleton with pyproject.toml, .env.example, and src/ directory structure
    - Create `pyproject.toml` with dependencies: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic, httpx, feedparser, trafilatura, structlog, pydantic-settings
    - Create dev dependencies: pytest, pytest-asyncio, hypothesis, respx, httpx
    - Create `.env.example` with all environment variables: DATABASE_URL, APP_HOST, APP_PORT, REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT_SECONDS, USER_AGENT
    - Create directory structure: `src/`, `src/data/`, `src/services/`, `src/routes/`, `scripts/`, `tests/`, `alembic/`
    - Add `__init__.py` files to all Python packages
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 1.2 Implement configuration loading with pydantic-settings
    - Create `src/config.py` with a `Settings` class reading from environment variables
    - Include DATABASE_URL (required), APP_HOST (default "0.0.0.0"), APP_PORT (default 8000), REQUEST_DELAY_SECONDS (default 1.0), REQUEST_TIMEOUT_SECONDS (default 30), USER_AGENT (default string)
    - Raise clear error on missing required variables
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 1.3 Set up SQLAlchemy async engine, session factory, and Base
    - Create `src/data/database.py` with async engine creation from DATABASE_URL, async session factory, and declarative Base
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 1.4 Define SQLAlchemy ORM models (Website, Feed, Article)
    - Create `src/data/models.py` with Website, Feed, Article models matching the design schema
    - Website: id, name (unique), url (unique), domain (indexed), created_at, updated_at, last_discovery_at, discovery_status (default "pending")
    - Feed: id, website_id (FK, indexed), feed_url, title, feed_type, created_at, last_parsed_at; unique constraint on (website_id, feed_url)
    - Article: id, feed_id (FK, indexed), url, title, author, published_at, summary, original_html, extracted_text, status (default "pending", indexed), feedparser_raw_entry (JSON), created_at, updated_at; unique constraint on (feed_id, url)
    - Define cascade deletes: Website → Feed → Article
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 1.5 Write property test for unique constraints (Property 11)
    - **Property 11: Unique constraints prevent duplicates at database level**
    - Test that inserting duplicate feed_url for same website_id or duplicate article url for same feed_id raises IntegrityError
    - **Validates: Requirements 6.5**

  - [x] 1.6 Define Pydantic request/response schemas
    - Create `src/data/schemas.py` with: WebsiteCreate, WebsiteResponse, FeedResponse, ArticleResponse, ArticleDetailResponse, PaginatedResponse[T], BatchSummaryResponse, DiscoveryResponse, ParseResponse, ExtractBatchResponse, ErrorResponse, StatusResponse
    - Use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility
    - _Requirements: 6.1, 6.2, 6.3, 9.1_

  - [x] 1.7 Set up Alembic for database migrations
    - Initialize Alembic with async PostgreSQL support
    - Create `alembic.ini` and `alembic/env.py` configured to use DATABASE_URL from environment
    - Generate initial migration from ORM models
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 2. Implement rate limiter and core services
  - [x] 2.1 Implement rate limiter service
    - Create `src/services/rate_limiter.py` with `RateLimiter` class
    - Per-domain delay tracking using in-memory dict with domain → last_request_time
    - `async def acquire(domain: str)` that waits until delay_seconds have passed since last request to that domain
    - Use `asyncio.Lock` per domain and `time.monotonic()` for timing
    - Handle 429 responses with Retry-After header support
    - _Requirements: 10.1, 10.3_

  - [ ]* 2.2 Write property test for rate limiter delay (Property 17)
    - **Property 17: Rate limiter enforces per-domain delay**
    - For any sequence of N requests to the same domain, elapsed time between consecutive requests >= configured delay
    - **Validates: Requirements 10.1**

  - [ ]* 2.3 Write property test for 429 retry-after handling (Property 19)
    - **Property 19: 429 responses trigger retry-after delay**
    - For any 429 response with Retry-After header, next request to that domain is delayed by at least the specified duration
    - **Validates: Requirements 10.3**

  - [x] 2.4 Implement feed discovery service
    - Create `src/services/discovery_service.py` with `FeedDiscoveryService` class
    - Accept httpx.AsyncClient and RateLimiter in constructor
    - `discover_feeds(website, db)`: fetch homepage HTML, parse `<link rel="alternate">` tags for RSS/Atom, probe common paths (/feed, /rss, /atom.xml, /feed.xml, /rss.xml, /index.xml, /feeds/all.atom.xml)
    - Validate candidate URLs return valid feed content
    - Store new feeds (skip existing via unique constraint), update website.last_discovery_at and discovery_status
    - On network error: return error, do NOT modify existing feed records, set discovery_status to "error"
    - Send configurable User-Agent header on all external requests
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 10.2_

  - [ ]* 2.5 Write property test for feed discovery link extraction (Property 6)
    - **Property 6: Feed discovery extracts and stores feed links from HTML**
    - For any HTML with `<link>` RSS/Atom tags, discovery stores each linked feed URL associated with the correct website
    - **Validates: Requirements 2.1, 2.3**

  - [ ]* 2.6 Write property test for discovery error preservation (Property 7)
    - **Property 7: Discovery network errors preserve existing data**
    - For any website with existing feeds, a failed discovery attempt leaves existing feed records unchanged
    - **Validates: Requirements 2.5**

  - [ ]* 2.7 Write property test for User-Agent header (Property 18)
    - **Property 18: User-Agent header is sent on all external requests**
    - For any outgoing HTTP request, User-Agent header is present and matches configured value
    - **Validates: Requirements 10.2**

  - [x] 2.8 Implement feed parser service
    - Create `src/services/parser_service.py` with `FeedParserService` class
    - Accept RateLimiter in constructor
    - `parse_feed(feed, db)`: use feedparser to retrieve and parse feed, extract title/link/published/author/summary from each entry, store raw entry as JSON in feedparser_raw_entry
    - Create new Article records for new entries (skip duplicates matched by URL via unique constraint)
    - Update feed.last_parsed_at
    - On unreachable/invalid feed: return error with details
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 2.9 Write property test for feed parsing metadata extraction (Property 8)
    - **Property 8: Feed parsing extracts all metadata fields**
    - For any valid RSS/Atom entry with title, link, published, author, summary, the article record matches the entry values
    - **Validates: Requirements 3.2**

  - [ ]* 2.10 Write property test for feed parsing idempotency (Property 9)
    - **Property 9: Feed parsing is idempotent**
    - For any feed, parsing N times produces the same article set; count does not increase after first parse
    - **Validates: Requirements 3.3, 3.4**

  - [x] 2.11 Implement article extractor service
    - Create `src/services/extractor_service.py` with `ArticleExtractorService` class
    - Accept httpx.AsyncClient and RateLimiter in constructor
    - `extract_article(article, db)`: download HTML, store in original_html, extract text via Trafilatura, store in extracted_text, update status
    - Status transitions: pending → extracted (success), pending → downloaded (HTML ok, extraction failed), pending → failed (download failed)
    - `extract_feed_articles(feed, db)`: extract all unprocessed articles for a feed, return summary dict
    - Send configurable User-Agent header
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 10.2_

  - [ ]* 2.12 Write property test for article extraction (Property 10)
    - **Property 10: Article extraction stores HTML and extracts text with correct status**
    - For any article with valid extractable HTML: original_html non-null, extracted_text non-null, status = "extracted"
    - **Validates: Requirements 4.1, 4.3, 4.4**

  - [x] 2.13 Implement batch processor service
    - Create `src/services/batch_service.py` with `BatchProcessor` class
    - Accept FeedParserService and ArticleExtractorService in constructor
    - `process_website(website, db)`: parse all feeds, then extract all new articles; continue on individual failures
    - `process_all(db)`: process all registered websites
    - Return BatchSummary with feeds_parsed, articles_discovered, articles_extracted, errors list
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 2.14 Write property test for batch coverage (Property 12)
    - **Property 12: Batch processing covers all feeds and new articles**
    - For any website with N feeds, batch summary's feeds_parsed equals N
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 2.15 Write property test for batch summary accuracy (Property 13)
    - **Property 13: Batch summary accurately reports counts including errors**
    - For K failures out of M articles, summary reports articles_extracted = M - K and errors has K entries
    - **Validates: Requirements 5.3, 5.4**

- [ ] 3. Checkpoint - Ensure all service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement API routes and FastAPI application
  - [ ] 4.1 Create FastAPI app entry point with middleware and lifespan
    - Create `src/main.py` with FastAPI app, lifespan handler for DB engine and httpx client setup/teardown
    - Add request ID middleware (UUID4 per request, added to response headers and structlog context)
    - Add global exception handler returning consistent ErrorResponse JSON
    - Configure structured logging with structlog
    - Include all route routers
    - _Requirements: 9.1, 9.2_

  - [ ] 4.2 Implement website routes
    - Create `src/routes/websites.py` with APIRouter prefix `/api/websites`
    - POST `/api/websites`: register website (name + url), return 201 or existing record if duplicate
    - GET `/api/websites`: list with pagination (page, size params)
    - GET `/api/websites/{id}`: get single website, 404 if not found
    - DELETE `/api/websites/{id}`: delete website, return 204
    - POST `/api/websites/{id}/discover`: trigger feed discovery
    - GET `/api/websites/{id}/feeds`: list feeds for website
    - GET `/api/websites/{id}/articles`: list articles across all feeds with pagination and status filter
    - Add OpenAPI summaries and response schemas to all endpoints
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.6, 2.7, 3.7, 7.4, 13.3_

  - [ ]* 4.3 Write property tests for website registration (Properties 1, 2, 3)
    - **Property 1: Website registration creates a record** — For any valid URL, registration returns an id and subsequent lookup returns the same record
    - **Validates: Requirements 1.1**
    - **Property 2: Website registration is idempotent** — Registering same URL N times returns same ID, count stays 1
    - **Validates: Requirements 1.2, 6.5**
    - **Property 3: Invalid input returns validation error** — Invalid URLs return 422 with error and message fields
    - **Validates: Requirements 1.3, 9.3**

  - [ ]* 4.4 Write property test for pagination (Property 4)
    - **Property 4: Pagination returns correct totals**
    - For N websites and page size S, page P returns at most S items, total = N, pages = ceil(N/S)
    - **Validates: Requirements 1.4**

  - [ ]* 4.5 Write property test for delete (Property 5)
    - **Property 5: Delete removes website**
    - After deleting a website, GET returns 404 and total count decreases by 1
    - **Validates: Requirements 1.5**

  - [ ] 4.6 Implement feed routes
    - Create `src/routes/feeds.py` with APIRouter
    - POST `/api/feeds/{id}/parse`: parse single feed
    - POST `/api/websites/{id}/parse`: parse all feeds for website
    - Add OpenAPI summaries and response schemas
    - _Requirements: 3.6, 3.7, 13.3_

  - [ ] 4.7 Implement article routes
    - Create `src/routes/articles.py` with APIRouter
    - GET `/api/articles/{id}`: get article with all fields (ArticleDetailResponse)
    - GET `/api/feeds/{id}/articles`: list articles for feed with pagination and status filter
    - POST `/api/articles/{id}/extract`: extract single article
    - DELETE `/api/articles/{id}`: delete article, return 204
    - POST `/api/feeds/{id}/extract`: extract all unprocessed articles for feed
    - Add OpenAPI summaries and response schemas
    - _Requirements: 4.7, 4.8, 7.1, 7.2, 7.3, 13.3_

  - [ ]* 4.8 Write property test for article status filtering (Property 14)
    - **Property 14: Article status filtering returns only matching articles**
    - For mixed-status articles and any filter value, listing returns only matching articles
    - **Validates: Requirements 7.2, 7.3, 7.4**

  - [ ] 4.9 Implement batch routes
    - Create `src/routes/batch.py` with APIRouter prefix `/api/batch`
    - POST `/api/batch/process`: process all websites
    - POST `/api/batch/process/{website_id}`: process single website
    - Add OpenAPI summaries and response schemas
    - _Requirements: 5.5, 13.3_

  - [ ] 4.10 Implement health and status routes
    - Create `src/routes/health.py` with APIRouter
    - GET `/health`: return 200 if DB connection works, 503 if unavailable
    - GET `/status`: return pipeline statistics (total websites, feeds, articles, articles by status)
    - Add OpenAPI summaries and response schemas
    - _Requirements: 8.1, 8.2, 8.3, 13.3_

  - [ ]* 4.11 Write property test for status endpoint counts (Property 15)
    - **Property 15: Status endpoint returns accurate counts**
    - For any DB state, /status counts match actual database totals
    - **Validates: Requirements 8.3**

  - [ ]* 4.12 Write property test for error response structure (Property 16)
    - **Property 16: Error responses have consistent structure**
    - For any error-triggering request, response JSON contains error and message string fields
    - **Validates: Requirements 9.1**

  - [ ]* 4.13 Write property test for OpenAPI completeness (Property 23)
    - **Property 23: OpenAPI spec has summaries and schemas for all endpoints**
    - For every endpoint in the spec, summary is non-empty and at least one response schema is defined
    - **Validates: Requirements 13.3**

- [ ] 5. Checkpoint - Ensure all API tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement CLI client and infrastructure
  - [ ] 6.1 Create the bash CLI script (scripts/feed-parser.sh)
    - Implement POSIX-compatible shell script with curl + jq
    - Read FEED_PARSER_API_URL from environment (default http://localhost:8000)
    - Implement all commands: add, list, list articles, discover, parse, parse --all, extract, extract --all, run, run --all, article, article delete, status, delete, help
    - Support `--name=<name> --source=<url>` named flags for add command
    - Auto-prepend https:// to URLs without protocol prefix
    - Name-to-ID resolution via GET /api/websites + jq filtering
    - Support --json flag for raw JSON output on all commands
    - Support --help flag on all commands and subcommands
    - Human-readable error display with HTTP status code on stderr
    - Make script executable (chmod +x)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12, 12.13, 12.14, 12.15, 12.16, 12.17, 12.18, 12.19_

  - [ ]* 6.2 Write property tests for CLI (Properties 20, 21, 22)
    - **Property 20: CLI auto-prepends https:// to bare URLs** — URLs without protocol get https:// prepended
    - **Validates: Requirements 12.3**
    - **Property 21: CLI --json flag outputs valid JSON** — All commands with --json produce parseable JSON
    - **Validates: Requirements 12.18**
    - **Property 22: CLI displays API errors with status code** — Error output contains HTTP status code and error message
    - **Validates: Requirements 12.17**

  - [ ] 6.3 Create Dockerfile with multi-stage build
    - Build stage: install dependencies from pyproject.toml, copy source
    - Production stage: slim base image, copy only needed files
    - Follow Dockerfile optimization rules: .dockerignore, dependency layer first, deterministic install
    - _Requirements: 11.1_

  - [ ] 6.4 Create docker-compose.yml for local development
    - App service with env_file: .env, port mapping matching fly.toml
    - PostgreSQL service with volume for data persistence
    - restart: unless-stopped
    - _Requirements: 11.1_

  - [ ] 6.5 Create fly.toml and fly-setup.sh for Fly.io deployment
    - fly.toml with app name, non-sensitive env vars in [env] section, port configuration
    - fly-setup.sh: parse APP_NAME from fly.toml, create app if needed, read .env, skip keys in fly.toml [env], set remaining as fly secrets
    - Make fly-setup.sh executable
    - _Requirements: 11.1, 11.2_

  - [ ] 6.6 Create .dockerignore
    - Exclude .git, __pycache__, .venv, tests, docs, .env, IDE files, alembic/versions
    - _Requirements: 11.1_

  - [ ] 6.7 Create README.md with setup and deployment instructions
    - Local Docker setup section (copy .env.example, docker compose up)
    - Fly.io deployment section (fly-setup.sh, fly deploy)
    - CLI usage section with examples
    - API endpoint summary
    - _Requirements: 13.2_

  - [ ] 6.8 Create API documentation markdown file
    - List all endpoints with method, path, description, request/response examples
    - _Requirements: 13.1, 13.2_

- [ ] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (23 properties total)
- Unit tests validate specific examples and edge cases
- The implementation language is Python with FastAPI, as specified in the design
