# Implementation Plan: AI News Agent

## Overview

Build a Python FastAPI service that indexes rss-feed articles into a Qdrant vector store and provides intelligent question-answering via a LangGraph-based RAG agent. The agent retrieves relevant article chunks, generates answers with source citations using an LLM via OpenRouter, and traces all operations via LangSmith. Implementation proceeds bottom-up: project setup → data layer → embedding client → indexer → RAG retrieval → LangGraph agent → API routes → CLI → infrastructure.

## Tasks

- [x] 1. Set up project structure, configuration, and database foundation
  - [x] 1.1 Create project skeleton with pyproject.toml, .env.example, and src/ directory structure
    - Create `pyproject.toml` with dependencies: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, httpx, langchain-openai, langgraph, langsmith, qdrant-client, pydantic-settings, structlog
    - Create dev dependencies: pytest, pytest-asyncio, hypothesis, respx
    - Create `.env.example` with all environment variables documented with comments: DATABASE_URL, APP_PORT, OPENROUTER_API_KEY, LLM_MODEL, EMBEDDING_MODEL, EMBEDDING_API_URL, EMBEDDING_API_KEY, QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION, RAG_TOP_K, RAG_MAX_CHUNKS_PER_ARTICLE, CHUNK_SIZE, CHUNK_OVERLAP, LANGSMITH_API_KEY, LANGSMITH_PROJECT, LANGSMITH_TRACING, AI_AGENT_URL
    - Create directory structure: `src/`, `tests/`, `scripts/`
    - Add `__init__.py` files to all Python packages
    - _Requirements: 9.1–9.8, 11.5_

  - [x] 1.2 Implement configuration loading with pydantic-settings
    - Create `src/config.py` with a `Settings` class reading all env vars from the design
    - DATABASE_URL (required), OPENROUTER_API_KEY (required), APP_PORT (default 8001), LLM_MODEL (default "openai/gpt-4o-mini"), EMBEDDING_MODEL, EMBEDDING_API_URL, EMBEDDING_API_KEY (defaults to OPENROUTER_API_KEY), QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION, RAG_TOP_K, RAG_MAX_CHUNKS_PER_ARTICLE, CHUNK_SIZE, CHUNK_OVERLAP, LANGSMITH_API_KEY, LANGSMITH_PROJECT, LANGSMITH_TRACING
    - Fail with clear error naming the missing variable if DATABASE_URL or OPENROUTER_API_KEY is absent
    - _Requirements: 9.1–9.9_

  - [ ]* 1.3 Write property test for startup validation (Property 13)
    - **Property 13: Startup validation for required environment variables**
    - For any required env var (DATABASE_URL, OPENROUTER_API_KEY) that is missing, the application should fail to start and the error message should name the specific missing variable
    - **Validates: Requirements 9.9**

  - [x] 1.4 Set up SQLAlchemy async engine, session factory, and models
    - Create `src/database.py` with async engine creation from DATABASE_URL, async session factory
    - Create `src/models.py` with read-only Article model (mapping to existing `articles` table) and new `IndexedArticle` model with fields: article_id (PK, FK to articles.id), indexed_at, chunk_count
    - _Requirements: 1.1, 1.5_

  - [x] 1.5 Define Pydantic request/response schemas
    - Create `src/schemas.py` with all schemas from the design: QueryRequest, IndexRequest, SourceInfo, QueryResponse, IndexingResult, StatsResponse, HealthResponse, ErrorResponse, RetrievedChunk, AgentState
    - _Requirements: 5.1, 5.2, 5.6, 10.1_

- [x] 2. Implement embedding client and article indexer
  - [x] 2.1 Implement embedding client
    - Create `src/embeddings.py` with `EmbeddingClient` class
    - Thin wrapper around OpenAI-compatible `/v1/embeddings` endpoint using httpx
    - `embed_texts(texts: list[str]) -> list[list[float]]` for batch embedding
    - `embed_query(text: str) -> list[float]` for single query embedding
    - Raise `EmbeddingError` on API failure
    - _Requirements: 1.3, 3.1, 8.1–8.4_

  - [x] 2.2 Implement text chunking logic in the indexer
    - Create `src/indexer.py` with `ArticleIndexer` class
    - Implement `chunk_text(text, chunk_size, overlap)` that splits text into overlapping chunks preserving sentence boundaries
    - No chunk exceeds chunk_size by more than one sentence length, consecutive chunks overlap by approximately chunk_overlap characters
    - _Requirements: 1.2, 8.5_

  - [ ]* 2.3 Write property test for text chunking (Property 2)
    - **Property 2: Text chunking respects configuration**
    - For any non-empty text and valid chunk_size/chunk_overlap (overlap < chunk_size), chunks should: (a) not exceed chunk_size by more than one sentence, (b) overlap by approximately chunk_overlap chars, (c) reconstruct the original text when overlaps are removed
    - **Validates: Requirements 1.2, 8.5**

  - [x] 2.4 Implement article indexing pipeline
    - Complete `ArticleIndexer` with `index_articles(full_sync=False)` method
    - Read articles with `status = 'extracted'` from PG; in incremental mode skip already-indexed articles
    - Generate embeddings via EmbeddingClient, upsert to Qdrant with deterministic UUID (`uuid5(NAMESPACE, f"{article_id}:{chunk_index}")`)
    - Store payload: article_id, chunk_index, chunk_text, article_title, article_url, published_at, indexed_at
    - Record article_id in `indexed_articles` table on success
    - Log errors and skip affected articles without crashing on embedding API failure
    - Return `IndexingResult` with counts
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ]* 2.5 Write property test for article selection by indexing mode (Property 1)
    - **Property 1: Article selection by indexing mode**
    - For any set of articles with various statuses and indexing states, incremental mode processes only `status='extracted'` AND not in `indexed_articles`; full sync processes all `status='extracted'`
    - **Validates: Requirements 1.1, 1.7**

  - [ ]* 2.6 Write property test for indexing idempotence (Property 4)
    - **Property 4: Indexing idempotence**
    - For any already-indexed article, running the indexer again in incremental mode should not create duplicate entries in Qdrant or indexed_articles
    - **Validates: Requirements 1.5**

  - [ ]* 2.7 Write property test for chunk metadata completeness (Property 3)
    - **Property 3: Chunk metadata completeness round-trip**
    - For any indexed article, every Qdrant point contains payload fields article_id, chunk_index, chunk_text, article_title, article_url, published_at, indexed_at
    - **Validates: Requirements 1.4, 3.5**

- [x] 3. Checkpoint - Ensure indexer tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement RAG retrieval pipeline
  - [x] 4.1 Implement Qdrant collection setup
    - Add collection creation logic (cosine distance, HNSW indexing, configurable vector dimensions) to be called during app startup or first indexing run
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 4.2 Implement RAG retrieval
    - Create `src/rag.py` with `RAGPipeline` class
    - `retrieve(query, date_from=None, date_to=None)`: embed query, search Qdrant with cosine similarity, apply optional date range filter on published_at payload field, deduplicate by article_id (max `RAG_MAX_CHUNKS_PER_ARTICLE` chunks per article), return top-k `RetrievedChunk` objects ordered by descending score
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 4.3 Write property test for retrieval top-k and ordering (Property 5)
    - **Property 5: Retrieval respects top-k and ordering**
    - For any query and top_k config, retrieval returns at most top_k chunks ordered by descending similarity score
    - **Validates: Requirements 3.2**

  - [ ]* 4.4 Write property test for date range filtering (Property 6)
    - **Property 6: Date range filtering**
    - For any query with date_from/date_to, all returned chunks have published_at within the specified range
    - **Validates: Requirements 3.3**

  - [ ]* 4.5 Write property test for per-article deduplication cap (Property 7)
    - **Property 7: Per-article deduplication cap**
    - For any retrieval result and configured max_chunks_per_article, no single article_id appears more than max_chunks_per_article times
    - **Validates: Requirements 3.4**

- [x] 5. Implement LangGraph agent
  - [x] 5.1 Implement LangGraph agent workflow
    - Create `src/agent.py` with `NewsAgent` class
    - Define LangGraph `StateGraph` with `AgentState` and two nodes: `retrieve` → `generate`
    - `retrieve` node: call `RAGPipeline.retrieve()`, populate `retrieved_chunks` in state; parse time references from query and pass date constraints
    - `generate` node: build prompt with system instruction (answer based only on retrieved context, cite sources), retrieved chunk context, and user query; call LLM via `langchain_openai.ChatOpenAI` configured with OpenRouter base URL and API key; populate `answer` and `sources`
    - If no relevant chunks found, respond indicating no relevant news was found
    - Set HTTP-Referer and X-Title headers for OpenRouter
    - Implement retry on 429: wait 2 seconds, retry once, then raise
    - Return `AgentResponse` with answer, sources, metadata
    - _Requirements: 4.1–4.7, 7.1–7.5_

  - [x] 5.2 Configure LangSmith tracing
    - Set `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` from settings when LangSmith is configured
    - Include query text, retrieved chunk count, LLM model, token usage, and response latency in traces
    - Tag traces with LANGSMITH_PROJECT
    - Log warning at startup if LANGSMITH_API_KEY is not set; continue operating without tracing
    - _Requirements: 12.1–12.6_

- [x] 6. Implement API routes and FastAPI application
  - [x] 6.1 Create FastAPI app entry point with lifespan and error handling
    - Create `src/main.py` with FastAPI app, lifespan handler for DB engine, httpx client, Qdrant client, and embedding client setup/teardown
    - Add global exception handler returning consistent `ErrorResponse` JSON with error type, message, and timestamp
    - Configure structured logging with structlog (timestamp, level, component, context)
    - Log LLM request/response metadata (model, token count, latency) without full prompt/response content
    - _Requirements: 10.1–10.4_

  - [x] 6.2 Implement query endpoint
    - `POST /api/query`: accept `{"query": "..."}`, invoke NewsAgent, return `QueryResponse` with answer, sources, query, processing_time_ms
    - Return HTTP 422 on missing/empty query
    - Return HTTP 503 on LLM service unavailability
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.7_

  - [ ]* 6.3 Write property test for query response structure (Property 8)
    - **Property 8: Query response structure completeness**
    - For any successful query, JSON contains: answer (non-empty string), sources (array with title/url/published_at), query (matching original), processing_time_ms (positive number)
    - **Validates: Requirements 5.2, 5.7**

  - [ ]* 6.4 Write property test for empty query validation (Property 9)
    - **Property 9: Empty query validation**
    - For any empty or whitespace-only string, POST /api/query returns HTTP 422 and the agent is not invoked
    - **Validates: Requirements 5.3**

  - [x] 6.5 Implement index, stats, and health endpoints
    - `POST /api/index`: trigger indexing, accept optional `{"full_sync": false}`, return IndexingResult
    - `GET /api/stats`: return StatsResponse with total_articles_indexed, total_chunks, last_indexed_at from indexed_articles table
    - `GET /health`: return 200 with HealthResponse when DB and Qdrant are reachable; report individual component status
    - _Requirements: 1.8, 5.5, 5.6, 10.4_

  - [ ]* 6.6 Write property test for stats accuracy (Property 10)
    - **Property 10: Stats accuracy**
    - For any state of indexed_articles, /api/stats returns total_articles_indexed = row count, total_chunks = sum of chunk_count, last_indexed_at = max indexed_at
    - **Validates: Requirements 5.6**

  - [ ]* 6.7 Write property test for error response structure (Property 14)
    - **Property 14: Error response structure consistency**
    - For any API error (4xx or 5xx), JSON body contains error (string), message (string), and timestamp (ISO datetime)
    - **Validates: Requirements 10.1**

- [x] 7. Checkpoint - Ensure all API and agent tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement CLI client and infrastructure
  - [x] 8.1 Create the bash CLI script (scripts/ai-agent.sh)
    - Implement POSIX-compatible shell script with curl + jq
    - Read `AI_AGENT_URL` from environment (default `http://localhost:8001`)
    - Implement commands: `query "text"`, `query --json "text"`, `status`, `index`, `help`, `--help`
    - `query`: display answer text followed by numbered source list with title, URL, published date
    - `--json` flag: output raw JSON response
    - `status`: display indexing statistics
    - `index`: trigger article indexing
    - Display clear error messages with HTTP status code on stderr when server is unreachable
    - Make script executable (chmod +x)
    - _Requirements: 6.1–6.9_

  - [ ]* 8.2 Write property test for CLI source output (Property 11)
    - **Property 11: CLI output contains all source information**
    - For any agent response with sources, formatted output includes answer text and numbered list with title, URL, and publication date for each source
    - **Validates: Requirements 6.3**

  - [ ]* 8.3 Write property test for CLI JSON mode (Property 12)
    - **Property 12: CLI JSON mode round-trip**
    - For any agent response, CLI with --json outputs valid JSON structurally identical to the raw API response
    - **Validates: Requirements 6.4**

  - [x] 8.4 Create Dockerfile with multi-stage build
    - Build stage: Python slim base, install dependencies from pyproject.toml first (layer caching), then copy source
    - Production stage: slim base, copy only needed files
    - Follow Dockerfile optimization rules: .dockerignore, dependency layer first, deterministic install
    - _Requirements: 11.1_

  - [x] 8.5 Create docker-compose.yml for local development
    - App service with `env_file: .env`, port mapping for APP_PORT
    - Qdrant service with persistent volume for data storage
    - PostgreSQL connection via DATABASE_URL in .env (shared with rss-feed)
    - `restart: unless-stopped`
    - _Requirements: 2.7, 11.2_

  - [x] 8.6 Create fly.toml and fly-setup.sh for Fly.io deployment
    - `fly.toml` with app name, non-sensitive env vars in `[env]` section, port configuration
    - `fly-setup.sh`: parse APP_NAME from fly.toml, create app if needed, read .env, skip keys in fly.toml [env], set remaining as fly secrets
    - Make fly-setup.sh executable
    - _Requirements: 11.3, 11.4_

  - [x] 8.7 Create .dockerignore and .gitignore
    - .dockerignore: exclude .git, __pycache__, .venv, tests, .env, IDE files
    - .gitignore: exclude .env, .env.local, __pycache__, .venv, *.pyc
    - _Requirements: 11.1_

  - [x] 8.8 Create README.md with setup and deployment instructions
    - Local Docker setup section (copy .env.example, docker compose up)
    - Fly.io deployment section (fly-setup.sh, fly deploy)
    - CLI usage section with examples for all commands
    - API endpoint summary
    - _Requirements: 11.6_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (14 properties total)
- Unit tests validate specific examples and edge cases
- The implementation language is Python with FastAPI, as specified in the design
