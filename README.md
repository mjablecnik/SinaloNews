# Sinalo — AI News Aggregation & Analysis

A multi-service system that automatically discovers, extracts, classifies, groups, and serves news articles from RSS feeds. Includes an AI-powered question-answering agent using RAG (Retrieval-Augmented Generation) and a web frontend for browsing classified content.

## Architecture

```
rss-feed (port 8000)         article-classifier (port 8002)       article-reader (port 3000)
┌─────────────────────┐      ┌──────────────────────────────┐     ┌─────────────────────────┐
│ Discover RSS feeds  │      │ Classify articles via LLM    │     │ SvelteKit frontend      │
│ Parse feed entries  │─────▶│ Generate tags & summaries    │◀────│ Browse by category      │
│ Extract article text│      │ Assign importance scores     │     │ Read article details    │
│ Store in PostgreSQL │      │ Group related articles       │     │ View article groups     │
└─────────────────────┘      └──────────────────────────────┘     │ Save articles locally   │
         │                             │                          └─────────────────────────┘
         │                             │
         │         shared PostgreSQL   │
         │                             │
         ▼                             ▼
┌──────────────────────────────────────────────┐
│                  PostgreSQL                   │
└──────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│ rag-agent (port 8001)       │
│ Index articles into Qdrant  │
│ Answer questions via RAG    │
│ LangGraph + OpenRouter LLMs │
└─────────────────────────────┘
```

## Services

| Service | Tech Stack | Port | Fly.io App | Description |
|---------|-----------|------|------------|-------------|
| [rss-feed](rss-feed/README.md) | Python, FastAPI | 8000 | `sinalo-feed` | RSS/Atom feed discovery, parsing, and article text extraction |
| [article-classifier](article-classifier/README.md) | Python, FastAPI, LangGraph | 8002 | `sinalo-classifier` | LLM-based article classification, tagging, summarization, and grouping |
| [rag-agent](rag-agent/README.md) | Python, FastAPI, LangGraph, Qdrant | 8001 | `sinalo-rag-agent` | RAG-based question answering over collected articles |
| [article-reader](article-reader/README.md) | SvelteKit, TypeScript, Tailwind | 3000 | `sinalo-reader` | Web UI for browsing, reading, and saving classified articles |

## Data Flow

1. **rss-feed** discovers feeds on registered websites, parses entries, and extracts article text into PostgreSQL
2. **article-classifier** reads unprocessed articles, classifies them with LLM (tags, importance, summary), writes results back
3. **article-classifier** groups related articles within the same category by topic and generates consolidated summaries
4. **article-reader** fetches classified articles and groups from the classifier API and displays them in a web UI
5. **rag-agent** indexes articles into Qdrant and answers natural language questions with source citations

## Tech Stack

- **Backend**: Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL, structlog
- **Frontend**: SvelteKit 5, TypeScript, Tailwind CSS, Vite, adapter-static + nginx
- **AI/ML**: LangChain, LangGraph, OpenRouter LLMs, Qdrant vector store
- **Infrastructure**: Docker multi-stage builds, Fly.io

## CLI Tools

Each backend service includes a shell script CLI client for interacting with its API:

| Script | Location | Description |
|--------|----------|-------------|
| `feed-parser` | `rss-feed/scripts/feed-parser.sh` | Manage websites, discover feeds, parse & extract articles |
| `classifier` | `article-classifier/scripts/classifier.sh` | Trigger classification/grouping, list articles & groups |
| `rag-agent` | `rag-agent/scripts/rag-agent.sh` | Query the RAG agent, trigger indexing, check stats |

All CLI scripts load configuration from their service's `.env` file automatically. Run any script with `--help` for full usage.

```bash
# Examples
sh rss-feed/scripts/feed-parser.sh add mysite https://example.com
sh rss-feed/scripts/feed-parser.sh run --all
sh article-classifier/scripts/classifier.sh classify
sh article-classifier/scripts/classifier.sh group --date=2026-05-07
sh rag-agent/scripts/rag-agent.sh query "What happened in AI today?"
```

## Quick Start

Each service has its own local development setup. All Python services require a shared PostgreSQL database (provision one externally or use a managed instance).

### Prerequisites

- Docker
- A running PostgreSQL instance accessible from your machine
- An [OpenRouter](https://openrouter.ai) API key (for classifier and rag-agent)

### 1. RSS Feed Pipeline

```bash
cp rss-feed/.env.example rss-feed/.env
# Set DATABASE_URL in rss-feed/.env pointing to your PostgreSQL
docker compose -f rss-feed/docker-compose.yml up -d
# Run migrations
docker compose -f rss-feed/docker-compose.yml exec app python -m alembic upgrade head
```

### 2. Article Classifier

```bash
cp article-classifier/.env.example article-classifier/.env
# Set DATABASE_URL and OPENROUTER_API_KEY in article-classifier/.env
sh article-classifier/scripts/start-docker.sh
```

### 3. RAG Agent

```bash
cp rag-agent/.env.example rag-agent/.env
# Set DATABASE_URL, OPENROUTER_API_KEY, and QDRANT_URL in rag-agent/.env
docker compose -f rag-agent/docker-compose.yml up -d
```

### 4. Article Reader

```bash
cp article-reader/.env.example article-reader/.env
# Set PUBLIC_ARTICLE_API_URL (defaults to http://localhost:8002)
sh article-reader/scripts/start-docker.sh
```

See individual service READMEs for detailed setup, CLI usage, and configuration.

## Fly.io Deployment

All services deploy to Fly.io in the Frankfurt (fra) region. A root-level `deploy.sh` script orchestrates setup and deployment across all services.

### First-time setup

Create all Fly.io apps and set secrets from each service's `.env`:

```bash
./deploy.sh setup
```

### Deploy

```bash
# Deploy all services
./deploy.sh all

# Deploy individual services (rss and classifier also run migrations)
./deploy.sh rss          # rss-feed + migrations
./deploy.sh classifier   # article-classifier + migrations
./deploy.sh agent        # rag-agent
./deploy.sh reader       # article-reader
```

### deploy.sh reference

| Command | Description |
|---------|-------------|
| `./deploy.sh` | Deploy all services (default, no migrations) |
| `./deploy.sh all` | Same as above |
| `./deploy.sh rss` | Deploy rss-feed + run Alembic migrations |
| `./deploy.sh classifier` | Deploy article-classifier + run Alembic migrations |
| `./deploy.sh agent` | Deploy rag-agent only |
| `./deploy.sh reader` | Deploy article-reader only |
| `./deploy.sh setup` | Create Fly apps and set secrets for all services (run once) |

Note: The `all` command deploys all services but does **not** run migrations automatically. Use individual commands (`rss`, `classifier`) when you need migrations to run after deploy.

## Environment Variables

Each service uses `.env` files for configuration. Copy `.env.example` to `.env` in each service directory and fill in the required values.

Shared required variables:
- `DATABASE_URL` — PostgreSQL connection string (all Python services)
- `OPENROUTER_API_KEY` — OpenRouter API key (classifier, rag-agent)

Service-specific variables:
- `QDRANT_URL` / `QDRANT_API_KEY` — Qdrant vector store connection (rag-agent)
- `PUBLIC_ARTICLE_API_URL` — Classifier API URL for the frontend (article-reader)
- `LANGSMITH_API_KEY` — Optional LangSmith tracing (classifier, rag-agent)

See each service's `.env.example` for the full list of variables.
