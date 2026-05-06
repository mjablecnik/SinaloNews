#!/bin/sh
# Builds and runs the article-classifier Docker container locally.
# Reads .env for environment variables and exposes port 8002.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FLY_TOML="${PROJECT_DIR}/fly.toml"
ENV_FILE="${PROJECT_DIR}/.env"

if [ ! -f "$FLY_TOML" ]; then
    echo "Error: fly.toml not found at ${FLY_TOML}" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env not found at ${ENV_FILE}" >&2
    echo "Copy .env.example to .env and fill in the values." >&2
    exit 1
fi

APP_NAME=$(grep '^app\s*=' "$FLY_TOML" | head -1 | sed 's/^app\s*=\s*"\(.*\)"/\1/')
if [ -z "$APP_NAME" ]; then
    echo "Error: could not parse app name from fly.toml" >&2
    exit 1
fi

echo "Building Docker image: ${APP_NAME}..."
docker build -t "$APP_NAME" "$PROJECT_DIR"

echo "Stopping existing container (if any)..."
docker stop "$APP_NAME" 2>/dev/null || true
docker rm "$APP_NAME" 2>/dev/null || true

echo "Starting container: ${APP_NAME}..."
docker run -d \
    --name "$APP_NAME" \
    --env-file "$ENV_FILE" \
    -p 8002:8002 \
    "$APP_NAME"

echo "Container started. Service available at http://localhost:8002"
echo "Health check: http://localhost:8002/health"
