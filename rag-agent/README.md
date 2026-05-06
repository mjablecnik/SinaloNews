# AI News Agent

An AI-powered question-answering service over news articles collected by the rss-feed pipeline. Uses RAG (Retrieval-Augmented Generation) with Qdrant vector search and a LangGraph agent backed by OpenRouter LLMs.

## Architecture

- **Indexer** — reads extracted articles from PostgreSQL, chunks text, generates embeddings, upserts to Qdrant
- **LangGraph Agent** — orchestrates semantic retrieval and LLM-based answer generation with source citations
- **FastAPI Server** — HTTP API for querying, indexing, stats, and health checks
- **CLI Client** — bash script for terminal access

## Local Docker Setup

1. Copy the example env file and fill in required values:

```sh
cp .env.example .env
```

Edit `.env` and set at minimum:
- `DATABASE_URL` — connection string for the shared rss-feed PostgreSQL database
- `OPENROUTER_API_KEY` — API key from [openrouter.ai](https://openrouter.ai)

2. Start the services:

```sh
docker compose up -d
```

This starts the `rag-agent` service on port 8001 and a local Qdrant instance on port 6333 with a persistent volume.

3. Index articles:

```sh
./scripts/rag-agent.sh index
```

## CLI Usage

The CLI script (`scripts/rag-agent.sh`) communicates with the agent server. Set `AI_AGENT_URL` if the server is not on `http://localhost:8001`.

```sh
# Ask a question
./scripts/rag-agent.sh query "What happened in AI this week?"

# Ask and get raw JSON
./scripts/rag-agent.sh query --json "Latest news about Python"

# Show indexing statistics
./scripts/rag-agent.sh status

# Trigger article indexing
./scripts/rag-agent.sh index

# Show help
./scripts/rag-agent.sh help
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/query` | Query the agent. Body: `{"query": "..."}` |
| POST | `/api/index` | Trigger indexing. Body: `{"full_sync": false}` |
| GET | `/api/stats` | Indexing statistics |
| GET | `/health` | Health check (DB + Qdrant) |

### Example query

```sh
curl -X POST http://localhost:8001/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the latest developments in AI?"}'
```

## Fly.io Deployment

1. Install the [Fly CLI](https://fly.io/docs/getting-started/installing-flyctl/) and log in.

2. Run the setup script (creates the app and sets secrets from `.env`):

```sh
./scripts/fly-setup.sh
```

3. Deploy:

```sh
fly deploy
```

The app name and non-sensitive config are defined in `fly.toml`. Secrets (API keys, `DATABASE_URL`) are set via `fly secrets`.

## Environment Variables

See `.env.example` for full documentation of all variables.

Required:
- `DATABASE_URL` — PostgreSQL connection string
- `OPENROUTER_API_KEY` — OpenRouter API key

Optional highlights:
- `LLM_MODEL` — LLM model via OpenRouter (default: `openai/gpt-4o-mini`)
- `QDRANT_URL` — Qdrant URL (default: `http://localhost:6333`)
- `LANGSMITH_API_KEY` — enable LangSmith tracing
