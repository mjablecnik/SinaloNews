# RSS Feed Pipeline

Discover RSS/Atom feeds on registered websites, parse entries, and extract article text via Trafilatura. Exposed as a REST API with a bash CLI client.

## Quick Start (Docker)

```sh
cp .env.example .env
# Edit .env and set DATABASE_URL (the docker-compose default works out of the box)
docker compose up
```

The API is available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

### Default DATABASE_URL for docker-compose

```
DATABASE_URL=postgresql+asyncpg://rss:rss@db:5432/rss_feed
```

### Run database migrations

```sh
docker compose exec app alembic upgrade head
```

## CLI Usage

The CLI requires `curl` and `jq`. Make it available on your PATH:

```sh
ln -s "$(pwd)/scripts/feed-parser.sh" /usr/local/bin/feed-parser
```

Set the API URL (optional, defaults to `http://localhost:8000`):

```sh
export FEED_PARSER_API_URL=http://localhost:8000
```

### Commands

```sh
# Register a website
feed-parser add "Hacker News" news.ycombinator.com

# List all websites
feed-parser list

# Discover RSS feeds on a website
feed-parser discover "Hacker News"

# Parse feeds (create article records)
feed-parser parse "Hacker News"
feed-parser parse --all

# Download and extract article text
feed-parser extract "Hacker News"
feed-parser extract --all

# Full pipeline (parse + extract)
feed-parser run "Hacker News"
feed-parser run --all

# List articles for a website
feed-parser list articles "Hacker News"

# Show a single article
feed-parser article 42

# Delete an article
feed-parser article delete 42

# Pipeline statistics
feed-parser status

# Delete a website
feed-parser delete "Hacker News"

# Help
feed-parser help
feed-parser help add
```

All commands support `--json` for raw JSON output and `--help` for usage details.

## Fly.io Deployment

1. Install the [Fly CLI](https://fly.io/docs/hands-on/install-flyctl/).
2. Log in: `fly auth login`
3. Run the setup script (creates app, sets secrets from `.env`):

```sh
./scripts/fly-setup.sh
```

4. Deploy:

```sh
fly deploy
```

5. Run migrations:

```sh
fly ssh console -C "alembic upgrade head"
```

## API Endpoints

See [docs/api.md](docs/api.md) for the full endpoint reference.

Interactive API docs are also available at `/docs` when the server is running.

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | *(required)* | PostgreSQL connection string |
| `APP_HOST` | `0.0.0.0` | Server bind host |
| `APP_PORT` | `8000` | Server port |
| `REQUEST_DELAY_SECONDS` | `1.0` | Per-domain rate limit delay |
| `REQUEST_TIMEOUT_SECONDS` | `30` | HTTP request timeout |
| `USER_AGENT` | `RSSFeedPipeline/1.0 …` | User-Agent header for crawling |
