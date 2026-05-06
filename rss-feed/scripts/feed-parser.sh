#!/bin/sh
# feed-parser.sh — CLI client for RSS Feed Pipeline API

# ── .env loading ─────────────────────────────────────────────────────────────

_script_dir="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
_env_file="${_script_dir}/../.env"
[ ! -f "$_env_file" ] && _env_file="./.env"
if [ -f "$_env_file" ]; then
    eval $(grep -v '^\s*#' "$_env_file" | grep -v '^\s*$' | sed 's/\r$//' | sed "s/'/'\\\\''/g" | sed "s/=\(.*\)/='\1'/" | sed 's/^/export /')
fi

API_URL="${FEED_PARSER_API_URL:-http://localhost:8000}"
JSON_OUTPUT=0

# ── core helpers ─────────────────────────────────────────────────────────────

die() { printf '%s\n' "$*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command '$1' not found."
}
require_cmd curl
require_cmd jq

# HTTP helpers — single request, body + status code separated
_api_call() {
    _method="$1"; shift
    _path="$1"; shift
    _tmpfile=$(mktemp)
    if [ "$_method" = "POST" ]; then
        _code=$(curl -s -o "$_tmpfile" -w '%{http_code}' -X POST \
            -H "Content-Type: application/json" -d "${1:-{\}}" "$API_URL$_path")
    elif [ "$_method" = "DELETE" ]; then
        _code=$(curl -s -o "$_tmpfile" -w '%{http_code}' -X DELETE "$API_URL$_path")
    else
        _code=$(curl -s -o "$_tmpfile" -w '%{http_code}' "$API_URL$_path")
    fi
    _body=$(cat "$_tmpfile")
    rm -f "$_tmpfile"
    printf '%s\n%s' "$_body" "$_code"
}

api_get()    { _api_call GET "$1"; }
api_post()   { _api_call POST "$1" "$2"; }
api_delete() { _api_call DELETE "$1"; }

parse_response() {
    code=$(printf '%s\n' "$1" | tail -n 1)
    body=$(printf '%s\n' "$1" | sed '$d')
}

check_error() {
    if [ "$1" -ge 400 ] 2>/dev/null; then
        msg=$(printf '%s' "$2" | jq -r '.detail // .message // "Unknown error"' 2>/dev/null || echo "$2")
        printf 'HTTP %s: %s\n' "$1" "$msg" >&2
        exit 1
    fi
}

# Call API, parse response, check for errors. Sets $body and $code.
api_request() {
    _method="$1"; _path="$2"; _data="$3"
    resp=$(_api_call "$_method" "$_path" "$_data")
    parse_response "$resp"
    check_error "$code" "$body"
}

# Output body as JSON or formatted
out_json() { printf '%s\n' "$body"; }
out_fmt()  { printf '%s\n' "$body" | jq -r "$1"; }

# Parse common flags from args. Sets: name, all, art_id (depending on context)
# Usage: parse_args "$@"; remaining positional arg is in $name
parse_flags() {
    _all=0; name=""; art_id=""
    for arg in "$@"; do
        case "$arg" in
            --all)  _all=1 ;;
            --json) JSON_OUTPUT=1 ;;
            --help|-h) return 1 ;;
            --name=*) name="${arg#--name=}" ;;
            --source=*) _source="${arg#--source=}" ;;
            -*) die "Unknown flag: $arg" ;;
            *) if [ -z "$name" ]; then name="$arg"; else art_id="$arg"; fi ;;
        esac
    done
    return 0
}

# Resolve website name to ID
resolve_name() {
    api_request GET "/api/websites?size=100"
    _id=$(printf '%s' "$body" | jq -r --arg n "$1" '.items[] | select(.name == $n) | .id' 2>/dev/null | head -n 1)
    [ -z "$_id" ] && die "Website '$1' not found. Use 'feed-parser list' to see registered websites."
    printf '%s' "$_id"
}

prepend_https() {
    case "$1" in
        http://*|https://*) printf '%s' "$1" ;;
        *) printf 'https://%s' "$1" ;;
    esac
}

# ── usage ────────────────────────────────────────────────────────────────────

usage_main() {
    cat <<'EOF'
Usage: feed-parser <command> [options]

Commands:
  add <name> <url>          Register a new website
  list                      List all registered websites
  list articles <name>      List all articles for a website
  discover <name>           Trigger RSS feed discovery
  parse <name|--all>        Parse feeds
  extract <name|--all>      Extract articles
  run <name|--all>          Full pipeline (parse + extract)
  article <id>              Show article details
  article delete <id>       Delete an article
  status                    Show pipeline statistics
  delete <name>             Delete a website
  help [command]            Show help

Global flags:
  --json    Raw JSON output
  --help    Show help

Environment:
  FEED_PARSER_API_URL    API base URL (default: http://localhost:8000)
EOF
}

usage_cmd() {
    case "$1" in
        add) cat <<'EOF'
Usage: feed-parser add <name> <url>
       feed-parser add --name=<name> --source=<url>

Register a new website. https:// is prepended if no protocol given.

Examples:
  feed-parser add echo24 https://echo24.cz
  feed-parser add --name=BBC --source=bbc.com
EOF
;;
        list) cat <<'EOF'
Usage: feed-parser list
       feed-parser list articles <name>

List websites or articles for a website.

Examples:
  feed-parser list
  feed-parser list articles echo24
EOF
;;
        discover) cat <<'EOF'
Usage: feed-parser discover <name>

Trigger RSS/Atom feed discovery for a website.
EOF
;;
        parse) cat <<'EOF'
Usage: feed-parser parse <name>
       feed-parser parse --all

Parse feeds and create article records.
EOF
;;
        extract) cat <<'EOF'
Usage: feed-parser extract <name>
       feed-parser extract --all

Download and extract unprocessed articles.
EOF
;;
        run) cat <<'EOF'
Usage: feed-parser run <name>
       feed-parser run --all

Run the full pipeline (parse + extract).
EOF
;;
        article) cat <<'EOF'
Usage: feed-parser article <id>
       feed-parser article delete <id>

Show or delete an article.
EOF
;;
        status) cat <<'EOF'
Usage: feed-parser status

Show pipeline statistics.
EOF
;;
        delete) cat <<'EOF'
Usage: feed-parser delete <name>

Delete a website and all its feeds and articles.
EOF
;;
        *) usage_main ;;
    esac
}

# ── commands ─────────────────────────────────────────────────────────────────

cmd_add() {
    name=""; _source=""
    for arg in "$@"; do
        case "$arg" in
            --name=*) name="${arg#--name=}" ;;
            --source=*) _source="${arg#--source=}" ;;
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_cmd add; exit 0 ;;
            -*) die "Unknown flag: $arg" ;;
            *) if [ -z "$name" ]; then name="$arg"; elif [ -z "$_source" ]; then _source="$arg"; fi ;;
        esac
    done
    [ -z "$name" ] && die "Missing name. Run 'feed-parser help add'."
    [ -z "$_source" ] && die "Missing url. Run 'feed-parser help add'."
    _source=$(prepend_https "$_source")
    payload=$(jq -n --arg n "$name" --arg u "$_source" '{name: $n, url: $u}')
    api_request POST "/api/websites" "$payload"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        _id=$(printf '%s' "$body" | jq -r '.id')
        if [ "$code" = "200" ]; then printf 'Already registered (id=%s)\n' "$_id"
        else
            printf 'Registered (id=%s)\n' "$_id"
            out_fmt '"  name:   \(.name)\n  url:    \(.url)\n  status: \(.discovery_status)"'
            printf 'Discovering feeds...\n'
            api_request POST "/api/websites/$_id/discover"
            out_fmt '"  Found \(.feeds_found) feed(s)"'
            printf '%s\n' "$body" | jq -r '.feeds[] | "    \(.feed_type // "feed"): \(.feed_url)"' 2>/dev/null
            return
        fi
        out_fmt '"  name:   \(.name)\n  url:    \(.url)\n  status: \(.discovery_status)"'
    fi
}

cmd_list() {
    if [ "$1" = "articles" ]; then
        shift
        parse_flags "$@" || { usage_cmd list; exit 0; }
        [ -z "$name" ] && die "Missing website name. Run 'feed-parser help list'."
        id=$(resolve_name "$name")
        api_request GET "/api/websites/$id/articles?size=100"
        if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
            out_fmt '"Articles for \"'$name'\" (total: \(.total))"'
            out_fmt '.items[] | "  [\(.id)] \(.status | ascii_upcase) \(.title // "(no title)") — \(.url)"'
        fi
        return
    fi
    parse_flags "$@" || { usage_cmd list; exit 0; }
    api_request GET "/api/websites?size=100"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        out_fmt '"Websites (total: \(.total))"'
        out_fmt '.items[] | "  [\(.id)] \(.name) — \(.url) [\(.discovery_status)]"'
    fi
}

cmd_discover() {
    parse_flags "$@" || { usage_cmd discover; exit 0; }
    [ -z "$name" ] && die "Missing website name. Run 'feed-parser help discover'."
    id=$(resolve_name "$name")
    api_request POST "/api/websites/$id/discover"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        out_fmt '"Discovery complete: \(.feeds_found) feed(s) found"'
        out_fmt '.feeds[] | "  \(.feed_type // "feed"): \(.feed_url)"'
    fi
}

cmd_parse() {
    parse_flags "$@" || { usage_cmd parse; exit 0; }
    if [ "$_all" = "1" ]; then
        api_request POST "/api/batch/process"
        if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
            out_fmt '"Batch: feeds_parsed=\(.feeds_parsed) articles_discovered=\(.articles_discovered) errors=\(.errors | length)"'
        fi
        return
    fi
    [ -z "$name" ] && die "Missing website name or --all. Run 'feed-parser help parse'."
    id=$(resolve_name "$name")
    api_request POST "/api/websites/$id/parse"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        out_fmt '"Parse: articles_found=\(.articles_found) new=\(.new_articles)"'
    fi
}

cmd_extract() {
    parse_flags "$@" || { usage_cmd extract; exit 0; }
    if [ "$_all" = "1" ]; then
        api_request POST "/api/batch/process"
        if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
            out_fmt '"Extract: articles_extracted=\(.articles_extracted) errors=\(.errors | length)"'
        fi
        return
    fi
    [ -z "$name" ] && die "Missing website name or --all. Run 'feed-parser help extract'."
    id=$(resolve_name "$name")
    api_request GET "/api/websites/$id/feeds"
    feeds=$(printf '%s' "$body" | jq -r '.[].id')
    total_extracted=0; total_errors=0
    for fid in $feeds; do
        api_request POST "/api/feeds/$fid/extract" || true
        extracted=$(printf '%s' "$body" | jq -r '.extracted // 0')
        errs=$(printf '%s' "$body" | jq -r '.errors | length')
        total_extracted=$((total_extracted + extracted))
        total_errors=$((total_errors + errs))
    done
    if [ "$JSON_OUTPUT" = "1" ]; then
        jq -n --argjson e "$total_extracted" --argjson err "$total_errors" '{articles_extracted: $e, errors: $err}'
    else
        printf 'Extract: articles_extracted=%s errors=%s\n' "$total_extracted" "$total_errors"
    fi
}

cmd_run() {
    parse_flags "$@" || { usage_cmd run; exit 0; }
    if [ "$_all" = "1" ]; then
        api_request POST "/api/batch/process"
    else
        [ -z "$name" ] && die "Missing website name or --all. Run 'feed-parser help run'."
        id=$(resolve_name "$name")
        api_request POST "/api/batch/process/$id"
    fi
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        out_fmt '"Pipeline: feeds_parsed=\(.feeds_parsed) discovered=\(.articles_discovered) extracted=\(.articles_extracted) errors=\(.errors | length)"'
    fi
}

cmd_article() {
    if [ "$1" = "delete" ]; then
        shift
        parse_flags "$@" || { usage_cmd article; exit 0; }
        [ -z "$name" ] && die "Missing article id. Run 'feed-parser help article'."
        api_request DELETE "/api/articles/$name"
        printf 'Article %s deleted.\n' "$name"
        return
    fi
    parse_flags "$@" || { usage_cmd article; exit 0; }
    [ -z "$name" ] && die "Missing article id. Run 'feed-parser help article'."
    api_request GET "/api/articles/$name"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        out_fmt '"Article #\(.id)\n  title:   \(.title // "(none)")\n  url:     \(.url)\n  status:  \(.status)\n  author:  \(.author // "(none)")\n  published: \(.published_at // "(unknown)")"'
        has_text=$(printf '%s' "$body" | jq -r '.extracted_text != null')
        if [ "$has_text" = "true" ]; then
            printf '\n--- Extracted Text ---\n'
            printf '%s\n' "$body" | jq -r '.extracted_text' | head -n 30
        fi
    fi
}

cmd_status() {
    parse_flags "$@" || { usage_cmd status; exit 0; }
    api_request GET "/status"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        out_fmt '"Status\n  websites:  \(.total_websites)\n  feeds:     \(.total_feeds)\n  articles:  \(.total_articles)\n    pending:    \(.articles_by_status.pending // 0)\n    extracted:  \(.articles_by_status.extracted // 0)\n    downloaded: \(.articles_by_status.downloaded // 0)\n    failed:     \(.articles_by_status.failed // 0)"'
    fi
}

cmd_delete() {
    parse_flags "$@" || { usage_cmd delete; exit 0; }
    [ -z "$name" ] && die "Missing website name. Run 'feed-parser help delete'."
    id=$(resolve_name "$name")
    api_request DELETE "/api/websites/$id"
    printf 'Website "%s" (id=%s) deleted.\n' "$name" "$id"
}

# ── dispatch ─────────────────────────────────────────────────────────────────

cmd=""; args=""
for arg in "$@"; do
    case "$arg" in
        --json) JSON_OUTPUT=1 ;;
        --help|-h) usage_main; exit 0 ;;
        *) if [ -z "$cmd" ]; then cmd="$arg"; else args="$args $arg"; fi ;;
    esac
done

case "$cmd" in
    add)      eval "cmd_add $args" ;;
    list)     eval "cmd_list $args" ;;
    discover) eval "cmd_discover $args" ;;
    parse)    eval "cmd_parse $args" ;;
    extract)  eval "cmd_extract $args" ;;
    run)      eval "cmd_run $args" ;;
    article)  eval "cmd_article $args" ;;
    status)   eval "cmd_status $args" ;;
    delete)   eval "cmd_delete $args" ;;
    help)     eval "usage_cmd $args" ;;
    "")       usage_main; exit 0 ;;
    *)        die "Unknown command: $cmd. Run 'feed-parser help'." ;;
esac
