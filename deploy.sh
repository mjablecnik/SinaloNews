#!/bin/sh
# deploy.sh — Deploy rss-feed and ai-agent services to Fly.io
# Usage:
#   ./deploy.sh          Deploy both services
#   ./deploy.sh rss      Deploy only rss-feed
#   ./deploy.sh agent    Deploy only ai-agent
#   ./deploy.sh setup    Run fly-setup.sh for both (create apps + set secrets)

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

deploy_rss() {
    echo "=== Deploying rss-feed-pipeline ==="
    cd "$ROOT_DIR/rss-feed"
    fly deploy
    echo "=== rss-feed-pipeline deployed ==="
    echo ""
}

deploy_agent() {
    echo "=== Deploying ai-news-agent ==="
    cd "$ROOT_DIR/ai-agent"
    fly deploy
    echo "=== ai-news-agent deployed ==="
    echo ""
}

setup_rss() {
    echo "=== Setting up rss-feed-pipeline ==="
    cd "$ROOT_DIR/rss-feed"
    sh scripts/fly-setup.sh
    echo ""
}

setup_agent() {
    echo "=== Setting up ai-news-agent ==="
    cd "$ROOT_DIR/ai-agent"
    sh scripts/fly-setup.sh
    echo ""
}

run_migrations_rss() {
    echo "=== Running rss-feed migrations ==="
    APP_NAME=$(grep '^app\s*=' "$ROOT_DIR/rss-feed/fly.toml" | head -1 | sed 's/^app\s*=\s*"\(.*\)"/\1/')
    fly ssh console --app "$APP_NAME" -C "python -m alembic upgrade head"
    echo ""
}

case "${1:-all}" in
    rss)
        deploy_rss
        run_migrations_rss
        ;;
    agent)
        deploy_agent
        ;;
    setup)
        setup_rss
        setup_agent
        ;;
    all)
        deploy_rss
        run_migrations_rss
        deploy_agent
        ;;
    *)
        echo "Usage: ./deploy.sh [rss|agent|setup|all]"
        echo ""
        echo "  rss     Deploy rss-feed-pipeline only"
        echo "  agent   Deploy ai-news-agent only"
        echo "  setup   Create Fly apps and set secrets (run once)"
        echo "  all     Deploy both services (default)"
        exit 1
        ;;
esac

echo "Done."
