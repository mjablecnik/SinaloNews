# Article Classifier

A FastAPI microservice that classifies articles using LLM (LangGraph/LangChain + OpenRouter). It reads unprocessed articles from the shared PostgreSQL database, generates hierarchical topic tags, assigns a content type and importance score, and produces a Czech-language summary.

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
| `LANGSMITH_API_KEY`       | No       | —                     | LangSmith API key for tracing        |
| `LANGSMITH_PROJECT`       | No       | `sinalo-classifier`   | LangSmith project name               |
| `LANGSMITH_TRACING`       | No       | `true`                | Enable LangSmith tracing             |

See `.env.example` for a complete template with comments.
