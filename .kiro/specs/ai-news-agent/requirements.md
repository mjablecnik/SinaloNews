# Requirements Document

## Introduction

An AI-powered news agent that provides intelligent question-answering over articles collected by the existing rss-feed pipeline. The system uses Retrieval-Augmented Generation (RAG) to index extracted article text into a Qdrant vector store, then uses a LangGraph-based agent to retrieve relevant articles and generate coherent answers with source citations. The agent runs as a Docker-based HTTP service, accessed via a CLI client or direct API calls. LLM access is provided through OpenRouter (OpenAI-compatible API). All LLM calls and agent workflows are traced via LangSmith for debugging and monitoring.

## Glossary

- **Agent_Server**: The FastAPI-based HTTP service that hosts the LangGraph agent and exposes a query endpoint
- **RAG_Pipeline**: The component responsible for embedding article text and storing/retrieving vectors for semantic search
- **Vector_Store**: A Qdrant vector database instance that stores article embeddings for similarity search
- **LangSmith**: The LangChain observability platform used for tracing, debugging, and monitoring LLM calls and agent workflows
- **Indexer**: The component that reads articles from the existing rss-feed database, generates embeddings, and upserts them into the Vector_Store
- **LangGraph_Agent**: The LangGraph-based agent that orchestrates retrieval, reasoning, and response generation
- **Embedding_Model**: The model used to convert text into vector representations for semantic search
- **LLM**: The large language model accessed via OpenRouter for generating natural language answers
- **CLI_Client**: A bash shell script that sends prompts to the Agent_Server via curl and displays results formatted with jq
- **Article**: An article record from the rss-feed database containing extracted_text, title, url, published_at, and other metadata
- **Chunk**: A segment of article text created by splitting long articles for embedding, stored with metadata linking back to the source article

## Requirements

### Requirement 1: Article Indexing

**User Story:** As a user, I want articles from the rss-feed pipeline to be indexed into a vector store, so that the AI agent can perform semantic search over them.

#### Acceptance Criteria

1. WHEN the Indexer is triggered, THE Indexer SHALL read all articles with status "extracted" from the rss-feed database that have not yet been indexed
2. WHEN an article's extracted_text exceeds the configured chunk size, THE Indexer SHALL split the text into overlapping chunks while preserving sentence boundaries
3. THE Indexer SHALL generate vector embeddings for each chunk using the configured Embedding_Model
4. THE Indexer SHALL store each embedding in the Vector_Store along with metadata including article_id, article_title, article_url, published_at, and chunk_index
5. WHEN an article is successfully indexed, THE Indexer SHALL record the article_id as indexed to prevent duplicate processing
6. IF the Embedding_Model is unreachable, THEN THE Indexer SHALL log the error and skip the affected articles without crashing
7. THE Indexer SHALL support both a one-time full sync and an incremental mode that only processes new articles since the last run
8. THE Agent_Server SHALL expose an endpoint to trigger indexing on demand

### Requirement 2: Vector Store Setup

**User Story:** As a user, I want the vector store to use Qdrant, so that I get a purpose-built vector database with advanced filtering and high-performance similarity search.

#### Acceptance Criteria

1. THE RAG_Pipeline SHALL use a Qdrant instance for vector storage and similarity search
2. THE RAG_Pipeline SHALL create a dedicated collection for storing article chunk embeddings with payload fields: article_id, chunk_index, chunk_text, article_title, article_url, published_at, indexed_at
3. THE RAG_Pipeline SHALL configure the collection with cosine distance metric and HNSW indexing for efficient approximate nearest neighbor search
4. THE RAG_Pipeline SHALL support configurable embedding dimensions to accommodate different embedding models
5. THE RAG_Pipeline SHALL connect to Qdrant using the `QDRANT_URL` environment variable (default: `http://localhost:6333`)
6. THE RAG_Pipeline SHALL optionally authenticate with Qdrant using the `QDRANT_API_KEY` environment variable when connecting to a cloud or secured instance
7. THE docker-compose.yml SHALL include a Qdrant service for local development, with a persistent volume for data storage

### Requirement 3: Semantic Retrieval

**User Story:** As a user, I want the agent to retrieve the most relevant article chunks for my query, so that answers are grounded in actual news content.

#### Acceptance Criteria

1. WHEN a query is received, THE RAG_Pipeline SHALL generate an embedding for the query text using the same Embedding_Model used for indexing
2. THE RAG_Pipeline SHALL perform a cosine similarity search against the Vector_Store and return the top-k most relevant chunks (configurable, default: 10)
3. THE RAG_Pipeline SHALL support filtering retrieved chunks by published_at date range when a time constraint is specified in the query
4. THE RAG_Pipeline SHALL deduplicate results so that no more than a configurable maximum number of chunks from the same article are returned (default: 3)
5. THE RAG_Pipeline SHALL return chunk text along with article metadata (title, url, published_at) for each retrieved result

### Requirement 4: LangGraph Agent

**User Story:** As a user, I want an intelligent agent that can reason about my query, retrieve relevant articles, and generate a coherent answer with sources, so that I get useful news summaries.

#### Acceptance Criteria

1. THE LangGraph_Agent SHALL use LangGraph to define a stateful agent workflow with retrieval and generation steps
2. WHEN a user query is received, THE LangGraph_Agent SHALL embed the query, retrieve relevant chunks from the Vector_Store, and generate a response using the LLM
3. THE LangGraph_Agent SHALL include a system prompt instructing the LLM to answer based only on the retrieved context and cite sources
4. THE LangGraph_Agent SHALL include source article URLs and titles in the response for every piece of information referenced
5. IF no relevant articles are found for a query, THEN THE LangGraph_Agent SHALL respond indicating that no relevant news was found in the indexed articles
6. THE LangGraph_Agent SHALL support a configurable LLM model name via environment variable to allow switching between models available on OpenRouter
7. WHEN the query includes a time reference (e.g., "last 24 hours", "this week"), THE LangGraph_Agent SHALL pass the time constraint to the retrieval step to filter by publication date

### Requirement 5: Agent Server API

**User Story:** As a user, I want an HTTP API to send queries to the agent and receive structured JSON responses, so that I can integrate the agent with other tools.

#### Acceptance Criteria

1. THE Agent_Server SHALL expose a POST endpoint at `/api/query` that accepts a JSON body with a "query" field (string, required)
2. WHEN a valid query is received, THE Agent_Server SHALL return a JSON response containing: "answer" (string), "sources" (array of objects with "title", "url", "published_at"), and "query" (the original query string)
3. IF the query field is missing or empty, THEN THE Agent_Server SHALL return HTTP 422 with a descriptive validation error
4. IF the LLM service is unreachable, THEN THE Agent_Server SHALL return HTTP 503 with an error message indicating the service is temporarily unavailable
5. THE Agent_Server SHALL expose a GET endpoint at `/health` that returns HTTP 200 when the service is operational and can connect to both the database and Qdrant
6. THE Agent_Server SHALL expose a GET endpoint at `/api/stats` that returns indexing statistics including total articles indexed, total chunks, and last indexing timestamp
7. THE Agent_Server SHALL include request processing time in the query response metadata

### Requirement 6: CLI Client

**User Story:** As a user, I want a command-line tool to send queries to the agent and see formatted results in my terminal, so that I can quickly get news summaries without using curl.

#### Acceptance Criteria

1. THE CLI_Client SHALL be implemented as a POSIX-compatible shell script (`scripts/ai-agent.sh`) using curl for HTTP requests and jq for JSON formatting, invokable as `ai-agent` via symlink or PATH
2. THE CLI_Client SHALL accept a query as a positional argument: `ai-agent query "what happened in IT today"`
3. WHEN a successful response is received, THE CLI_Client SHALL display the answer text followed by a numbered list of source links with titles and publication dates
4. THE CLI_Client SHALL support a `--json` flag to output the raw JSON response instead of formatted text
5. THE CLI_Client SHALL read the agent server URL from the `AI_AGENT_URL` environment variable (default: `http://localhost:8001`)
6. IF the agent server is unreachable, THEN THE CLI_Client SHALL display a clear error message with the connection details and HTTP status code
7. THE CLI_Client SHALL support a `status` subcommand to display agent indexing statistics
8. THE CLI_Client SHALL support an `index` subcommand to trigger article indexing on the server
9. THE CLI_Client SHALL support `ai-agent help` and `ai-agent --help` to display a summary of all available commands

### Requirement 7: LLM Integration via OpenRouter

**User Story:** As a user, I want the agent to use OpenRouter for LLM access, so that I can choose from multiple models without changing the code.

#### Acceptance Criteria

1. THE LangGraph_Agent SHALL connect to OpenRouter using the OpenAI-compatible API endpoint (https://openrouter.ai/api/v1)
2. THE LangGraph_Agent SHALL authenticate with OpenRouter using an API key provided via the `OPENROUTER_API_KEY` environment variable
3. THE LangGraph_Agent SHALL use a configurable model name via the `LLM_MODEL` environment variable (default: a cost-effective model suitable for summarization)
4. THE LangGraph_Agent SHALL set appropriate HTTP headers required by OpenRouter including `HTTP-Referer` and `X-Title`
5. IF the OpenRouter API returns a rate limit error, THEN THE LangGraph_Agent SHALL retry the request once after a 2-second delay before returning an error to the user

### Requirement 8: Embedding Configuration

**User Story:** As a user, I want configurable embedding generation, so that I can choose between different embedding providers based on cost and quality.

#### Acceptance Criteria

1. THE RAG_Pipeline SHALL support generating embeddings via OpenRouter or a compatible OpenAI-style embedding endpoint
2. THE RAG_Pipeline SHALL read the embedding model name from the `EMBEDDING_MODEL` environment variable
3. THE RAG_Pipeline SHALL read the embedding API endpoint from the `EMBEDDING_API_URL` environment variable (default: OpenRouter endpoint)
4. THE RAG_Pipeline SHALL read the embedding API key from the `EMBEDDING_API_KEY` environment variable (default: same as `OPENROUTER_API_KEY`)
5. THE RAG_Pipeline SHALL support configurable chunk size via `CHUNK_SIZE` environment variable (default: 1000 characters) and chunk overlap via `CHUNK_OVERLAP` environment variable (default: 200 characters)

### Requirement 9: Configuration

**User Story:** As a user, I want all service configuration managed through environment variables, so that I can adjust settings for different environments.

#### Acceptance Criteria

1. THE Agent_Server SHALL read the database connection string from the `DATABASE_URL` environment variable
2. THE Agent_Server SHALL read the HTTP server port from the `APP_PORT` environment variable (default: 8001)
3. THE Agent_Server SHALL read the OpenRouter API key from the `OPENROUTER_API_KEY` environment variable
4. THE Agent_Server SHALL read the LLM model from the `LLM_MODEL` environment variable
5. THE Agent_Server SHALL read retrieval parameters from environment variables: `RAG_TOP_K` (default: 10), `RAG_MAX_CHUNKS_PER_ARTICLE` (default: 3)
6. THE Agent_Server SHALL read the Qdrant connection URL from the `QDRANT_URL` environment variable (default: `http://localhost:6333`)
7. THE Agent_Server SHALL read the optional Qdrant API key from the `QDRANT_API_KEY` environment variable
8. THE Agent_Server SHALL read the Qdrant collection name from the `QDRANT_COLLECTION` environment variable (default: "article_chunks")
9. THE Agent_Server SHALL read LangSmith configuration from environment variables: `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` (default: "sinalo-agent"), `LANGSMITH_TRACING` (default: "true")
10. IF a required environment variable (DATABASE_URL, OPENROUTER_API_KEY) is missing, THEN THE Agent_Server SHALL fail to start with a clear error message indicating which variable is missing

### Requirement 10: Error Handling and Logging

**User Story:** As a user, I want consistent error handling and structured logging, so that I can diagnose issues when the agent fails.

#### Acceptance Criteria

1. WHEN any API endpoint encounters an unhandled error, THE Agent_Server SHALL return a JSON error response with a consistent structure including error type, message, and timestamp
2. THE Agent_Server SHALL log all operations with structured logging including timestamp, level, component name, and relevant context (query text, retrieval count, processing time)
3. THE Agent_Server SHALL log LLM request/response metadata (model used, token count, latency) without logging the full prompt or response content
4. IF the database connection is lost, THEN THE Agent_Server SHALL attempt to reconnect and return HTTP 503 for requests until the connection is restored

### Requirement 11: Deployment Infrastructure

**User Story:** As a user, I want the agent to run in Docker with Fly.io deployment support, so that it follows the same deployment pattern as the rss-feed service.

#### Acceptance Criteria

1. THE Agent_Server SHALL include a multi-stage Dockerfile optimized for Python with dependency layer caching
2. THE Agent_Server SHALL include a docker-compose.yml for local development with `env_file: .env` and a Qdrant service with persistent volume
3. THE Agent_Server SHALL include a fly.toml configuration for Fly.io deployment
4. THE Agent_Server SHALL include a fly-setup.sh script that parses the app name from fly.toml and sets secrets from .env
5. THE Agent_Server SHALL include .env.example with all required and optional environment variables documented with comments
6. THE Agent_Server SHALL include a README.md with setup instructions for both local Docker and Fly.io deployment

### Requirement 12: LangSmith Observability

**User Story:** As a user, I want all LLM calls and agent workflows traced in LangSmith, so that I can debug, monitor, and optimize the agent's behavior.

#### Acceptance Criteria

1. THE Agent_Server SHALL integrate with LangSmith for tracing all LangGraph agent runs, LLM calls, and embedding requests
2. THE Agent_Server SHALL configure LangSmith tracing via environment variables: `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and `LANGSMITH_TRACING`
3. WHEN `LANGSMITH_TRACING` is set to "true", THE Agent_Server SHALL send trace data to LangSmith for every query processed by the agent
4. THE Agent_Server SHALL include the query text, retrieved chunk count, LLM model used, token usage, and response latency in each LangSmith trace
5. IF the LangSmith API key is not configured or LangSmith is unreachable, THEN THE Agent_Server SHALL continue operating normally without tracing and log a warning at startup
6. THE Agent_Server SHALL tag each trace with the project name configured via `LANGSMITH_PROJECT` to organize traces in the LangSmith dashboard
