#!/bin/sh
# CLI client for the AI News Agent
# Usage: rag-agent <command> [options]

set -e

# Load .env file safely (skip comments, handle special chars)
_script_dir="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
_env_file="${_script_dir}/../.env"
if [ ! -f "$_env_file" ]; then
    _env_file="./.env"
fi
if [ -f "$_env_file" ]; then
    eval $(grep -v '^\s*#' "$_env_file" | grep -v '^\s*$' | sed 's/\r$//' | sed "s/'/'\\\\''/g" | sed "s/=\(.*\)/='\1'/" | sed 's/^/export /')
fi

AI_AGENT_URL="${AI_AGENT_URL:-http://localhost:8001}"

usage() {
    cat <<EOF
Usage: rag-agent <command> [options]

Commands:
  query [--json] "text"   Ask the agent a question
  status                  Show indexing statistics
  index                   Trigger article indexing
  help, --help            Show this help message

Options:
  --json    Output raw JSON response instead of formatted text

Environment:
  AI_AGENT_URL  Base URL of the agent server (default: http://localhost:8001)

Examples:
  rag-agent query "What happened in AI today?"
  rag-agent query --json "Latest news about Python"
  rag-agent status
  rag-agent index
EOF
}

require_jq() {
    if ! command -v jq >/dev/null 2>&1; then
        echo "Error: jq is required but not installed." >&2
        exit 1
    fi
}

require_curl() {
    if ! command -v curl >/dev/null 2>&1; then
        echo "Error: curl is required but not installed." >&2
        exit 1
    fi
}

do_query() {
    json_mode=0
    query_text=""

    while [ "$#" -gt 0 ]; do
        case "$1" in
            --json)
                json_mode=1
                shift
                ;;
            *)
                query_text="$1"
                shift
                ;;
        esac
    done

    if [ -z "$query_text" ]; then
        echo "Error: query text is required." >&2
        echo "Usage: rag-agent query [--json] \"your question\"" >&2
        exit 1
    fi

    require_curl
    require_jq

    escaped=$(printf '%s' "$query_text" | jq -Rs '.')
    payload="{\"query\":${escaped}}"

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "${AI_AGENT_URL}/api/query" 2>&1)

    http_code=$(printf '%s' "$response" | tail -n1)
    body=$(printf '%s' "$response" | head -n -1)

    if [ "$http_code" != "200" ]; then
        echo "Error: server returned HTTP ${http_code}" >&2
        echo "$body" >&2
        exit 1
    fi

    if [ "$json_mode" = "1" ]; then
        printf '%s\n' "$body"
        return
    fi

    answer=$(printf '%s' "$body" | jq -r '.answer')
    printf '%s\n\n' "$answer"

    source_count=$(printf '%s' "$body" | jq '.sources | length')
    if [ "$source_count" -gt 0 ]; then
        echo "Sources:"
        printf '%s' "$body" | jq -r '.sources | to_entries[] | "\(.key + 1). \(.value.title)\n   \(.value.url)\n   Published: \(.value.published_at // "unknown")"'
    fi
}

do_status() {
    json_mode=0
    if [ "$1" = "--json" ]; then
        json_mode=1
    fi

    require_curl
    require_jq

    response=$(curl -s -w "\n%{http_code}" \
        "${AI_AGENT_URL}/api/stats" 2>&1)

    http_code=$(printf '%s' "$response" | tail -n1)
    body=$(printf '%s' "$response" | head -n -1)

    if [ "$http_code" != "200" ]; then
        echo "Error: server returned HTTP ${http_code}" >&2
        echo "$body" >&2
        exit 1
    fi

    if [ "$json_mode" = "1" ]; then
        printf '%s\n' "$body"
        return
    fi

    total_articles=$(printf '%s' "$body" | jq -r '.total_articles_indexed')
    total_chunks=$(printf '%s' "$body" | jq -r '.total_chunks')
    last_indexed=$(printf '%s' "$body" | jq -r '.last_indexed_at // "never"')

    echo "Indexing Statistics:"
    echo "  Articles indexed: ${total_articles}"
    echo "  Total chunks:     ${total_chunks}"
    echo "  Last indexed at:  ${last_indexed}"
}

do_index() {
    json_mode=0
    if [ "$1" = "--json" ]; then
        json_mode=1
    fi

    require_curl
    require_jq

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d '{}' \
        "${AI_AGENT_URL}/api/index" 2>&1)

    http_code=$(printf '%s' "$response" | tail -n1)
    body=$(printf '%s' "$response" | head -n -1)

    if [ "$http_code" != "200" ]; then
        echo "Error: server returned HTTP ${http_code}" >&2
        echo "$body" >&2
        exit 1
    fi

    if [ "$json_mode" = "1" ]; then
        printf '%s\n' "$body"
        return
    fi

    processed=$(printf '%s' "$body" | jq -r '.articles_processed')
    chunks=$(printf '%s' "$body" | jq -r '.chunks_created')
    error_count=$(printf '%s' "$body" | jq -r '.errors | length')

    echo "Indexing complete:"
    echo "  Articles processed: ${processed}"
    echo "  Chunks created:     ${chunks}"
    if [ "$error_count" -gt 0 ]; then
        echo "  Errors:             ${error_count}"
        printf '%s' "$body" | jq -r '.errors[]' | while IFS= read -r err; do
            echo "    - ${err}"
        done
    fi
}

if [ "$#" -eq 0 ]; then
    usage
    exit 0
fi

command="$1"
shift

case "$command" in
    query)
        do_query "$@"
        ;;
    status)
        do_status "$@"
        ;;
    index)
        do_index "$@"
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "Error: unknown command '${command}'" >&2
        echo "Run 'rag-agent help' for usage." >&2
        exit 1
        ;;
esac
