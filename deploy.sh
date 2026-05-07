#!/bin/sh
# deploy.sh — Deploy rss-feed, rag-agent, article-classifier, and article-reader services to Fly.io
# Usage:
#   ./deploy.sh              Deploy all services
#   ./deploy.sh rss          Deploy only rss-feed
#   ./deploy.sh agent        Deploy only rag-agent
#   ./deploy.sh classifier   Deploy only article-classifier
#   ./deploy.sh reader       Deploy only article-reader
#   ./deploy.sh setup        Run fly-setup.sh for all (create apps + set secrets)

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
    cd "$ROOT_DIR/rag-agent"
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
    cd "$ROOT_DIR/rag-agent"
    sh scripts/fly-setup.sh
    echo ""
}

deploy_classifier() {
    echo "=== Deploying article-classifier ==="
    cd "$ROOT_DIR/article-classifier"
    fly deploy
    echo "=== article-classifier deployed ==="
    echo ""
}

setup_classifier() {
    echo "=== Setting up article-classifier ==="
    cd "$ROOT_DIR/article-classifier"
    sh scripts/fly-setup.sh
    echo ""
}

deploy_reader() {
    echo "=== Deploying article-reader ==="
    cd "$ROOT_DIR/article-reader"
    fly deploy
    echo "=== article-reader deployed ==="
    echo ""
}

setup_reader() {
    echo "=== Setting up article-reader ==="
    cd "$ROOT_DIR/article-reader"
    sh scripts/fly-setup.sh
    echo ""
}

run_migrations_classifier() {
    echo "=== Running article-classifier migrations ==="
    APP_NAME=$(grep '^app\s*=' "$ROOT_DIR/article-classifier/fly.toml" | head -1 | sed 's/^app\s*=\s*"\(.*\)"/\1/')
    fly ssh console --app "$APP_NAME" -C "python -m alembic upgrade head"
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
    classifier)
        deploy_classifier
        run_migrations_classifier
        ;;
    reader)
        deploy_reader
        ;;
    setup)
        setup_rss
        setup_agent
        setup_classifier
        setup_reader
        ;;
    all)
        deploy_rss
        run_migrations_rss
        deploy_agent
        deploy_classifier
        run_migrations_classifier
        deploy_reader
        ;;
    *)
        echo "Usage: ./deploy.sh [rss|agent|classifier|reader|setup|all]"
        echo ""
        echo "  rss          Deploy rss-feed-pipeline only"
        echo "  agent        Deploy ai-news-agent only"
        echo "  classifier   Deploy article-classifier only"
        echo "  reader       Deploy article-reader only"
        echo "  setup        Create Fly apps and set secrets (run once)"
        echo "  all          Deploy all services (default)"
        exit 1
        ;;
esac

echo "Done."
