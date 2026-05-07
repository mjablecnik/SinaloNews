#!/bin/sh
# classifier.sh — CLI client for Article Classifier API

# ── .env loading ─────────────────────────────────────────────────────────────

_script_dir="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
_env_file="${_script_dir}/../.env"
[ ! -f "$_env_file" ] && _env_file="./.env"
if [ -f "$_env_file" ]; then
    eval $(grep -v '^\s*#' "$_env_file" | grep -v '^\s*$' | sed 's/\r$//' | sed "s/'/'\\\\''/g" | sed "s/=\(.*\)/='\1'/" | sed 's/^/export /')
fi

API_URL="${CLASSIFIER_API_URL:-http://localhost:8002}"
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
    else
        _code=$(curl -s -o "$_tmpfile" -w '%{http_code}' "$API_URL$_path")
    fi
    _body=$(cat "$_tmpfile")
    rm -f "$_tmpfile"
    printf '%s\n%s' "$_body" "$_code"
}

api_get()  { _api_call GET "$1"; }
api_post() { _api_call POST "$1" "$2"; }

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

api_request() {
    _method="$1"; _path="$2"; _data="$3"
    resp=$(_api_call "$_method" "$_path" "$_data")
    parse_response "$resp"
    check_error "$code" "$body"
}

out_json() { printf '%s\n' "$body"; }
out_fmt()  { printf '%s\n' "$body" | jq -r "$1"; }

# ── usage ────────────────────────────────────────────────────────────────────

usage_main() {
    cat <<'EOF'
Usage: classifier <command> [options]

Commands:
  classify              Trigger classification of unprocessed articles
  status                Show classification processing status
  articles [options]    List classified articles with filters
  health                Check service health
  help [command]        Show help

Global flags:
  --json    Raw JSON output
  --help    Show help

Environment:
  CLASSIFIER_API_URL    API base URL (default: http://localhost:8002)
EOF
}

usage_cmd() {
    case "$1" in
        classify) cat <<'EOF'
Usage: classifier classify

Trigger classification of all unprocessed articles. Returns immediately
with the number of articles queued. Classification runs in the background.

Examples:
  classifier classify
  classifier classify --json
EOF
;;
        status) cat <<'EOF'
Usage: classifier status

Show current classification processing state: idle/processing,
number of pending articles, and number of classified articles.

Examples:
  classifier status
  classifier status --json
EOF
;;
        articles) cat <<'EOF'
Usage: classifier articles [options]

List classified articles with optional filtering, sorting, and pagination.

Filter options:
  --category=<cat>      Filter by main tag category (e.g. Technology)
  --subcategory=<sub>   Filter by tag subcategory (e.g. AI)
  --type=<type>         Filter by content type (e.g. BREAKING_NEWS)
  --min-score=<n>       Minimum importance score (0-10)
  --from=<date>         Date from (ISO format, e.g. 2025-01-01)
  --to=<date>           Date to (ISO format, e.g. 2025-12-31)

Sort options:
  --sort=<field>        Sort field: importance_score, published_at, classified_at
  --order=<dir>         Sort direction: asc or desc (default: desc)

Pagination:
  --page=<n>            Page number (default: 1)
  --size=<n>            Page size, max 100 (default: 20)

Output:
  --json                Raw JSON output

Examples:
  classifier articles
  classifier articles --min-score=7 --type=BREAKING_NEWS
  classifier articles --category=Technology --subcategory=AI --sort=importance_score
  classifier articles --category=Politics --subcategory=Czech --order=desc
  classifier articles --from=2025-01-01 --to=2025-06-01 --page=2 --size=10
  classifier articles --min-score=8 --json
EOF
;;
        health) cat <<'EOF'
Usage: classifier health

Check the health of the classifier service and its database connection.
Returns status "ok" or "unavailable".

Examples:
  classifier health
EOF
;;
        *) usage_main ;;
    esac
}

# ── commands ─────────────────────────────────────────────────────────────────

cmd_classify() {
    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_cmd classify; exit 0 ;;
            -*) die "Unknown flag: $arg" ;;
        esac
    done
    api_request POST "/api/classify"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        queued=$(printf '%s' "$body" | jq -r '.queued // 0')
        msg=$(printf '%s' "$body" | jq -r '.message // "Classification triggered"')
        printf '%s\n' "$msg"
    fi
}

cmd_status() {
    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_cmd status; exit 0 ;;
            -*) die "Unknown flag: $arg" ;;
        esac
    done
    api_request GET "/api/classify/status"
    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        out_fmt '"Status:      \(.status)\nPending:     \(.pending)\nClassified:  \(.classified)"'
    fi
}

cmd_articles() {
    _category=""; _subcategory=""; _type=""; _min_score=""
    _from=""; _to=""; _sort=""; _order=""; _page=""; _size=""

    for arg in "$@"; do
        case "$arg" in
            --category=*)    _category="${arg#--category=}" ;;
            --subcategory=*) _subcategory="${arg#--subcategory=}" ;;
            --type=*)        _type="${arg#--type=}" ;;
            --min-score=*)   _min_score="${arg#--min-score=}" ;;
            --from=*)        _from="${arg#--from=}" ;;
            --to=*)          _to="${arg#--to=}" ;;
            --sort=*)        _sort="${arg#--sort=}" ;;
            --order=*)       _order="${arg#--order=}" ;;
            --page=*)        _page="${arg#--page=}" ;;
            --size=*)        _size="${arg#--size=}" ;;
            --json)          JSON_OUTPUT=1 ;;
            --help|-h)       usage_cmd articles; exit 0 ;;
            -*)              die "Unknown flag: $arg" ;;
        esac
    done

    # Build query string
    _qs=""
    append_qs() { [ -n "$2" ] && _qs="${_qs}${_qs:+&}${1}=${2}"; }
    append_qs "category"     "$_category"
    append_qs "subcategory"  "$_subcategory"
    append_qs "content_type" "$_type"
    append_qs "min_score"    "$_min_score"
    append_qs "date_from"    "$_from"
    append_qs "date_to"      "$_to"
    append_qs "sort_by"      "$_sort"
    append_qs "sort_order"   "$_order"
    append_qs "page"         "$_page"
    append_qs "size"         "$_size"

    _path="/api/articles"
    [ -n "$_qs" ] && _path="${_path}?${_qs}"

    api_request GET "$_path"

    if [ "$JSON_OUTPUT" = "1" ]; then out_json; else
        total=$(printf '%s' "$body" | jq -r '.total')
        pages=$(printf '%s' "$body" | jq -r '.pages')
        page=$(printf '%s' "$body" | jq -r '.page')
        printf 'Articles (total: %s, page %s/%s)\n' "$total" "$page" "$pages"
        printf '%s\n' "$body" | jq -r '
            .items[] |
            "  [\(.importance_score)/10] \(.content_type) — \(.title // "(no title)")\n" +
            "    tags: \([.tags[] | "\(.category)/\(.subcategory)"] | join(", "))\n" +
            "    url:  \(.url)\n" +
            "    published: \(.published_at // "unknown")"
        ' 2>/dev/null
    fi
}

cmd_health() {
    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_cmd health; exit 0 ;;
            -*) die "Unknown flag: $arg" ;;
        esac
    done
    resp=$(api_get "/health")
    parse_response "$resp"
    if [ "$JSON_OUTPUT" = "1" ]; then printf '%s\n' "$body"; else
        _status=$(printf '%s' "$body" | jq -r '.status // "unknown"')
        printf 'Health: %s\n' "$_status"
        if [ "$code" != "200" ]; then exit 1; fi
    fi
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
    classify) eval "cmd_classify $args" ;;
    status)   eval "cmd_status $args" ;;
    articles) eval "cmd_articles $args" ;;
    health)   eval "cmd_health $args" ;;
    help)     eval "usage_cmd $args" ;;
    "")       usage_main; exit 0 ;;
    *)        die "Unknown command: $cmd. Run 'classifier help'." ;;
esac
