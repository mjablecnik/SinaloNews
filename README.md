# Sinalo — AI News Aggregation & Analysis

A two-service system that automatically discovers and extracts news articles from RSS feeds, then provides intelligent question-answering over the collected content using RAG (Retrieval-Augmented Generation).

## Architecture

```
rss-feed-pipeline (port 8000)          ai-news-agent (port 8001)
┌──────────────────────────┐           ┌──────────────────────────┐
│  Discover RSS feeds      │           │  Index articles into     │
│  Parse feed entries      │           │  Qdrant vector store     │
│  Extract article text    │──────────▶│  Answer questions via    │
│  Store in PostgreSQL     │  shared   │  LangGraph RAG agent     │
└──────────────────────────┘  Postgres └──────────────────────────┘
```

## Services

### rss-feed-pipeline

Discovers RSS/Atom feeds on registered websites, parses entries, downloads articles, and extracts clean text using Trafilatura. Exposes a REST API and includes a CLI client (`feed-parser.sh`).

Key flow: **Register website → Discover feeds → Parse entries → Extract article text**

### ai-news-agent

Reads extracted articles from PostgreSQL, chunks and embeds them into Qdrant, and answers user questions using a LangGraph agent with OpenRouter LLMs. Responses include source citations with links and publication dates.

Key flow: **Index articles → User asks question → Semantic search → LLM generates cited answer**

## Tech Stack

- Python 3.11+, FastAPI, SQLAlchemy (async), PostgreSQL, structlog
- feedparser, Trafilatura, httpx (rss-feed)
- Qdrant, LangChain, LangGraph, OpenRouter (rag-agent)

## Quick Start

Each service has its own `docker-compose.yml` for local development:

```bash
# 1. RSS Feed Pipeline
cp rss-feed/.env.example rss-feed/.env
docker compose -f rss-feed/docker-compose.yml up --build

# 2. AI News Agent
cp rag-agent/.env.example rag-agent/.env
# Set OPENROUTER_API_KEY in rag-agent/.env
docker compose -f rag-agent/docker-compose.yml up --build
```

See individual service READMEs for detailed setup, CLI usage, and Fly.io deployment instructions:
- [rss-feed/README.md](rss-feed/README.md)
- [rag-agent/README.md](rag-agent/README.md)
