# Article Classifier

A FastAPI microservice that classifies articles using LLM (LangGraph/LangChain + OpenRouter). It reads unprocessed articles from the shared PostgreSQL database, generates hierarchical topic tags, assigns a content type and importance score, and produces a Czech-language summary. Related articles are grouped together using RAG-based vector similarity.

## Requirements

- Docker (for local development)
- [Fly.io CLI](https://fly.io/docs/hands-on/install-flyctl/) (for deployment)
- `curl` and `jq` (for the CLI client)
- Access to the shared PostgreSQL database
- An [OpenRouter](https://openrouter.ai/) API key

## Local Docker Setup

1. Copy the example environment file and fill in the required values:

   ```sh
   cp .env.example .env
   ```

   Required variables:
   - `DATABASE_URL` — PostgreSQL connection string (points to the shared remote database)
   - `OPENROUTER_API_KEY` — OpenRouter API key for LLM calls

2. Start the service in Docker:

   ```sh
   sh scripts/start-docker.sh
   ```

   This builds the Docker image and runs the container on port `8002`. The service connects to the remote PostgreSQL database specified in `DATABASE_URL`.

3. Verify the service is running:

   ```sh
   sh scripts/classifier.sh health
   ```

## Fly.io Deployment

### First-time setup

Run the setup script once to create the Fly.io app and set secrets from `.env`:

```sh
sh scripts/fly-setup.sh
```

This will:
- Create the Fly.io app (`sinalo-classifier`) if it does not already exist
- Set all secrets from `.env` that are not already defined in `fly.toml [env]`

### Deploy

```sh
fly deploy
```

Or use the root deploy script to deploy all services:

```sh
# From the repository root
./deploy.sh classifier     # Deploy article-classifier only
./deploy.sh all            # Deploy all services
```

### Run database migrations

After deploying for the first time, run the Alembic migrations:

```sh
APP_NAME=$(grep '^app' fly.toml | sed 's/app = "\(.*\)"/\1/')
fly ssh console --app "$APP_NAME" -C "python -m alembic upgrade head"
```

Or via the root deploy script (migrations run automatically with `./deploy.sh classifier`).

## CLI Usage

The `scripts/classifier.sh` script provides a CLI client for the API.

Set the API URL via environment variable (defaults to `http://localhost:8002`):

```sh
export CLASSIFIER_API_URL=https://sinalo-classifier.fly.dev
```

### Trigger classification

```sh
sh scripts/classifier.sh classify
```

### Check classification status

```sh
sh scripts/classifier.sh status
```

### List classified articles

```sh
# All articles (default: sorted by classified_at desc, page 1, size 20)
sh scripts/classifier.sh articles

# Filter by tag category and subcategory
sh scripts/classifier.sh articles --category=Technology --subcategory=AI

# Filter by content type and minimum importance score
sh scripts/classifier.sh articles --type=BREAKING_NEWS --min-score=7

# Filter by date range
sh scripts/classifier.sh articles --from=2025-01-01 --to=2025-12-31

# Sort by importance score descending
sh scripts/classifier.sh articles --sort=importance_score --order=desc

# Paginate
sh scripts/classifier.sh articles --page=2 --size=10

# Raw JSON output
sh scripts/classifier.sh articles --min-score=8 --json
```

### Health check

```sh
sh scripts/classifier.sh health
```

## Article Grouping

The classifier groups related articles using RAG-based vector similarity rather than LLM clustering. This is a two-step process:

### Step 1: Similarity Matching (`POST /api/groups/generate`)

1. Fetches classified articles that haven't been indexed yet
2. Embeds each article's full text using `openai/text-embedding-3-small` via OpenRouter
3. Stores the embedding in a Qdrant collection (`article_full`)
4. Queries Qdrant for the most similar existing article
5. If similarity score >= threshold: adds the article to an existing group or creates a new group
6. If similarity score < threshold: the article remains standalone

```sh
sh scripts/classifier.sh group --date=2026-05-07
```

### Step 2: Detail Generation (`POST /api/groups/regenerate`)

Groups created or modified during similarity matching are flagged with `needs_regeneration`. The regenerate endpoint processes these groups:

1. Fetches all groups with `needs_regeneration = true`
2. Generates a Czech-language title, summary, and combined detail article using LLM
3. Clears the `needs_regeneration` flag on success

```sh
sh scripts/classifier.sh regenerate
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GROUPING_SIMILARITY_THRESHOLD` | `0.75` | Minimum cosine similarity (0.0–1.0) for grouping |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | — | Qdrant API key (optional) |
| `QDRANT_FULL_ARTICLE_COLLECTION` | `article_full` | Qdrant collection name |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding model via OpenRouter |
| `EMBEDDING_API_URL` | `https://openrouter.ai/api/v1` | Embedding API endpoint |

Higher threshold values produce fewer, tighter groups (only very similar articles). Lower values produce more, broader groups.

## Environment Variables

| Variable                  | Required | Default               | Description                          |
|---------------------------|----------|-----------------------|--------------------------------------|
| `DATABASE_URL`            | Yes      | —                     | PostgreSQL connection string         |
| `OPENROUTER_API_KEY`      | Yes      | —                     | OpenRouter API key                   |
| `APP_PORT`                | No       | `8002`                | Port the service listens on          |
| `LLM_MODEL`               | No       | `openai/gpt-4o-mini`  | LLM model via OpenRouter             |
| `BATCH_SIZE`              | No       | `20`                  | Articles per classification batch    |
| `LLM_RETRY_DELAY_SECONDS` | No       | `5`                   | Delay between LLM retries (seconds)  |
| `LLM_MAX_RETRIES`         | No       | `3`                   | Maximum LLM retry attempts           |
| `GROUPING_SIMILARITY_THRESHOLD` | No | `0.75`               | Cosine similarity threshold for grouping |
| `QDRANT_URL`              | No       | `http://localhost:6333` | Qdrant server URL                  |
| `QDRANT_API_KEY`          | No       | —                     | Qdrant API key                       |
| `QDRANT_FULL_ARTICLE_COLLECTION` | No | `article_full`       | Qdrant collection name               |
| `EMBEDDING_MODEL`         | No       | `openai/text-embedding-3-small` | Embedding model         |
| `EMBEDDING_API_URL`       | No       | `https://openrouter.ai/api/v1` | Embedding API endpoint   |
| `LANGSMITH_API_KEY`       | No       | —                     | LangSmith API key for tracing        |
| `LANGSMITH_PROJECT`       | No       | `sinalo-classifier`   | LangSmith project name               |
| `LANGSMITH_TRACING`       | No       | `true`                | Enable LangSmith tracing             |

See `.env.example` for a complete template with comments.
