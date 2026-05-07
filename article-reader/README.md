# Article Reader

A SvelteKit web application for browsing and reading classified news articles. Connects to the article-classifier API to display articles organized by category, with filtering and sorting capabilities.

## Features

- Browse articles by category and subcategory
- Filter by importance score and date range
- Sort by date or importance
- Read full article content with Markdown rendering
- Responsive design with Tailwind CSS
- Static site generation (served via nginx)

## Requirements

- Docker (for local development)
- [Fly.io CLI](https://fly.io/docs/hands-on/install-flyctl/) (for deployment)
- Node.js 22+ (for development without Docker)
- Access to the article-classifier API

## Local Docker Setup

1. Copy the example environment file and set the API URL:

   ```sh
   cp .env.example .env
   ```

   Required variables:
   - `PUBLIC_ARTICLE_API_URL` — URL of the article-classifier API (default: `http://localhost:8002`)

2. Start the service in Docker:

   ```sh
   sh scripts/start-docker.sh
   ```

   This builds the static site and serves it via nginx on port 3000.

3. Open the app at `http://localhost:3000`

## Local Development (without Docker)

```sh
cp .env.example .env
npm install
npm run dev
```

The dev server starts at `http://localhost:5173`.

## Fly.io Deployment

### First-time setup

Run the setup script once to create the Fly.io app and set secrets from `.env`:

```sh
sh scripts/fly-setup.sh
```

### Deploy

```sh
fly deploy
```

The `PUBLIC_ARTICLE_API_URL` build argument is configured in `fly.toml` and points to the production classifier API (`https://sinalo-classifier.fly.dev`).

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PUBLIC_ARTICLE_API_URL` | Yes | `http://localhost:8002` | Base URL for the article-classifier API |

See `.env.example` for the full template.

## Tech Stack

- SvelteKit 5 with static adapter
- TypeScript
- Tailwind CSS
- Vite
- nginx (production serving)
