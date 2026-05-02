#!/bin/sh
# feed-parser.sh — CLI client for RSS Feed Pipeline API

API_URL="${FEED_PARSER_API_URL:-http://localhost:8000}"
JSON_OUTPUT=0

# ── helpers ──────────────────────────────────────────────────────────────────

die() { printf '%s\n' "$*" >&2; exit 1; }

require_cmd() {
    command -v "$1" >/dev/null 2>&1 || die "Required command '$1' not found. Please install it."
}

require_cmd curl
require_cmd jq

api_get() {
    curl -sf -w '\n%{http_code}' "$API_URL$1"
}

api_post() {
    curl -sf -w '\n%{http_code}' -X POST -H "Content-Type: application/json" -d "${2:-{\}}" "$API_URL$1"
}

api_delete() {
    curl -sf -w '\n%{http_code}' -X DELETE "$API_URL$1"
}

# Split response body and status code (last line is the code)
parse_response() {
    body=$(printf '%s' "$1" | head -n -1)
    code=$(printf '%s' "$1" | tail -n 1)
}

check_error() {
    # $1 = http_code, $2 = body
    if [ "$1" -ge 400 ] 2>/dev/null; then
        msg=$(printf '%s' "$2" | jq -r '.detail // .message // "Unknown error"' 2>/dev/null || echo "$2")
        printf 'HTTP %s: %s\n' "$1" "$msg" >&2
        exit 1
    fi
}

output() {
    # $1 = raw JSON body
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$1"
    else
        printf '%s\n' "$1" | jq '.'
    fi
}

# Name-to-ID resolution: GET /api/websites and find by name field
resolve_name() {
    name="$1"
    resp=$(api_get "/api/websites?size=100")
    parse_response "$resp"
    check_error "$code" "$body"
    id=$(printf '%s' "$body" | jq -r --arg n "$name" '.items[] | select(.name == $n) | .id' 2>/dev/null | head -n 1)
    if [ -z "$id" ]; then
        die "Website '$name' not found. Use 'feed-parser list' to see registered websites."
    fi
    printf '%s' "$id"
}

prepend_https() {
    url="$1"
    case "$url" in
        http://*|https://*) printf '%s' "$url" ;;
        *) printf 'https://%s' "$url" ;;
    esac
}

# ── usage / help ──────────────────────────────────────────────────────────────

usage_main() {
    cat <<'EOF'
Usage: feed-parser <command> [options]

Commands:
  add <name> <url>          Register a new website (also: --name=<n> --source=<u>)
  list                      List all registered websites
  list articles <name>      List all articles for a website
  discover <name>           Trigger RSS feed discovery for a website
  parse <name>              Parse feeds for a website
  parse --all               Parse feeds for all websites
  extract <name>            Extract articles for a website
  extract --all             Extract articles for all websites
  run <name>                Full pipeline for a website (parse + extract)
  run --all                 Full pipeline for all websites
  article <id>              Show article details
  article delete <id>       Delete an article
  status                    Show pipeline statistics
  delete <name>             Delete a registered website
  help [command]            Show help for a command

Global flags:
  --json                    Output raw JSON instead of formatted text
  --help                    Show this help message

Environment:
  FEED_PARSER_API_URL       API base URL (default: http://localhost:8000)
EOF
}

usage_add() {
    cat <<'EOF'
Usage: feed-parser add <name> <url>
       feed-parser add --name=<name> --source=<url>

Register a new website for feed discovery.

Arguments:
  name    Human-readable name for the website
  url     Website URL (https:// is prepended if no protocol given)

Examples:
  feed-parser add "Hacker News" news.ycombinator.com
  feed-parser add --name="BBC" --source=https://bbc.com
EOF
}

usage_list() {
    cat <<'EOF'
Usage: feed-parser list
       feed-parser list articles <name>

Without arguments: list all registered websites.
With 'articles <name>': list all articles for that website.

Flags:
  --json    Output raw JSON

Examples:
  feed-parser list
  feed-parser list articles "Hacker News"
EOF
}

usage_discover() {
    cat <<'EOF'
Usage: feed-parser discover <name>

Trigger RSS/Atom feed discovery for a registered website.

Arguments:
  name    Website name (as registered with 'feed-parser add')

Examples:
  feed-parser discover "Hacker News"
EOF
}

usage_parse() {
    cat <<'EOF'
Usage: feed-parser parse <name>
       feed-parser parse --all

Parse feeds and create article records.

Arguments:
  name    Website name, or --all for every website

Examples:
  feed-parser parse "BBC"
  feed-parser parse --all
EOF
}

usage_extract() {
    cat <<'EOF'
Usage: feed-parser extract <name>
       feed-parser extract --all

Download and extract unprocessed articles.

Arguments:
  name    Website name, or --all for every website

Examples:
  feed-parser extract "BBC"
  feed-parser extract --all
EOF
}

usage_run() {
    cat <<'EOF'
Usage: feed-parser run <name>
       feed-parser run --all

Run the full pipeline (parse + extract) for one or all websites.

Arguments:
  name    Website name, or --all for every website

Examples:
  feed-parser run "BBC"
  feed-parser run --all
EOF
}

usage_article() {
    cat <<'EOF'
Usage: feed-parser article <id>
       feed-parser article delete <id>

Show or delete an article.

Arguments:
  id    Article ID

Examples:
  feed-parser article 42
  feed-parser article delete 42
EOF
}

usage_status() {
    cat <<'EOF'
Usage: feed-parser status

Show pipeline statistics: total websites, feeds, articles by status.

Examples:
  feed-parser status
EOF
}

usage_delete() {
    cat <<'EOF'
Usage: feed-parser delete <name>

Delete a registered website (and all its feeds and articles).

Arguments:
  name    Website name

Examples:
  feed-parser delete "Old Blog"
EOF
}

# ── command implementations ───────────────────────────────────────────────────

cmd_add() {
    name=""
    url=""
    # Parse flags or positional args
    for arg in "$@"; do
        case "$arg" in
            --name=*) name="${arg#--name=}" ;;
            --source=*) url="${arg#--source=}" ;;
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_add; exit 0 ;;
            -*) die "Unknown flag: $arg" ;;
            *) if [ -z "$name" ]; then name="$arg"; elif [ -z "$url" ]; then url="$arg"; fi ;;
        esac
    done
    [ -z "$name" ] && die "Missing required argument: name\nRun 'feed-parser help add' for usage."
    [ -z "$url" ] && die "Missing required argument: url\nRun 'feed-parser help add' for usage."
    url=$(prepend_https "$url")
    payload=$(jq -n --arg n "$name" --arg u "$url" '{name: $n, url: $u}')
    resp=$(api_post "/api/websites" "$payload")
    parse_response "$resp"
    check_error "$code" "$body"
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$body"
    else
        id=$(printf '%s' "$body" | jq -r '.id')
        wname=$(printf '%s' "$body" | jq -r '.name')
        wurl=$(printf '%s' "$body" | jq -r '.url')
        status=$(printf '%s' "$body" | jq -r '.discovery_status')
        if [ "$code" = "200" ]; then
            printf 'Website already registered (id=%s)\n' "$id"
        else
            printf 'Registered website (id=%s)\n' "$id"
        fi
        printf '  name:   %s\n' "$wname"
        printf '  url:    %s\n' "$wurl"
        printf '  status: %s\n' "$status"
    fi
}

cmd_list() {
    # list articles <name> or just list
    if [ "$1" = "articles" ]; then
        shift
        # consume --json / --help before name
        for arg in "$@"; do
            case "$arg" in
                --json) JSON_OUTPUT=1 ;;
                --help|-h) usage_list; exit 0 ;;
            esac
        done
        name=""
        for arg in "$@"; do
            case "$arg" in
                --json|--help|-h) ;;
                *) name="$arg" ;;
            esac
        done
        [ -z "$name" ] && die "Missing website name.\nRun 'feed-parser help list' for usage."
        id=$(resolve_name "$name")
        resp=$(api_get "/api/websites/$id/articles?size=100")
        parse_response "$resp"
        check_error "$code" "$body"
        if [ "$JSON_OUTPUT" = "1" ]; then
            printf '%s\n' "$body"
        else
            total=$(printf '%s' "$body" | jq -r '.total')
            printf 'Articles for "%s" (total: %s)\n' "$name" "$total"
            printf '%s\n' "$body" | jq -r '.items[] | "  [\(.id)] \(.status | ascii_upcase) \(.title // "(no title)") — \(.url)"'
        fi
        return
    fi

    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_list; exit 0 ;;
        esac
    done

    resp=$(api_get "/api/websites?size=100")
    parse_response "$resp"
    check_error "$code" "$body"
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$body"
    else
        total=$(printf '%s' "$body" | jq -r '.total')
        printf 'Websites (total: %s)\n' "$total"
        printf '%s\n' "$body" | jq -r '.items[] | "  [\(.id)] \(.name) — \(.url) [\(.discovery_status)]"'
    fi
}

cmd_discover() {
    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_discover; exit 0 ;;
        esac
    done
    name=""
    for arg in "$@"; do
        case "$arg" in
            --json|--help|-h) ;;
            *) name="$arg" ;;
        esac
    done
    [ -z "$name" ] && die "Missing website name.\nRun 'feed-parser help discover' for usage."
    id=$(resolve_name "$name")
    resp=$(api_post "/api/websites/$id/discover")
    parse_response "$resp"
    check_error "$code" "$body"
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$body"
    else
        found=$(printf '%s' "$body" | jq -r '.feeds_found')
        printf 'Discovery complete: %s feed(s) found\n' "$found"
        printf '%s\n' "$body" | jq -r '.feeds[] | "  \(.feed_type // "feed"): \(.feed_url)"'
    fi
}

cmd_parse() {
    all=0
    for arg in "$@"; do
        case "$arg" in
            --all) all=1 ;;
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_parse; exit 0 ;;
        esac
    done

    if [ "$all" = "1" ]; then
        resp=$(api_post "/api/batch/process")
        parse_response "$resp"
        check_error "$code" "$body"
        if [ "$JSON_OUTPUT" = "1" ]; then
            printf '%s\n' "$body"
        else
            printf '%s\n' "$body" | jq -r '"Batch parse complete: feeds_parsed=\(.feeds_parsed) articles_discovered=\(.articles_discovered) errors=\(.errors | length)"'
        fi
        return
    fi

    name=""
    for arg in "$@"; do
        case "$arg" in
            --all|--json|--help|-h) ;;
            *) name="$arg" ;;
        esac
    done
    [ -z "$name" ] && die "Missing website name or --all.\nRun 'feed-parser help parse' for usage."
    id=$(resolve_name "$name")
    resp=$(api_post "/api/websites/$id/parse")
    parse_response "$resp"
    check_error "$code" "$body"
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$body"
    else
        printf '%s\n' "$body" | jq -r '"Parse complete: articles_found=\(.articles_found) new_articles=\(.new_articles)"'
    fi
}

cmd_extract() {
    all=0
    for arg in "$@"; do
        case "$arg" in
            --all) all=1 ;;
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_extract; exit 0 ;;
        esac
    done

    if [ "$all" = "1" ]; then
        resp=$(api_post "/api/batch/process")
        parse_response "$resp"
        check_error "$code" "$body"
        if [ "$JSON_OUTPUT" = "1" ]; then
            printf '%s\n' "$body"
        else
            printf '%s\n' "$body" | jq -r '"Extract complete: articles_extracted=\(.articles_extracted) errors=\(.errors | length)"'
        fi
        return
    fi

    name=""
    for arg in "$@"; do
        case "$arg" in
            --all|--json|--help|-h) ;;
            *) name="$arg" ;;
        esac
    done
    [ -z "$name" ] && die "Missing website name or --all.\nRun 'feed-parser help extract' for usage."
    id=$(resolve_name "$name")
    # Get all feeds for website, then extract each
    resp=$(api_get "/api/websites/$id/feeds")
    parse_response "$resp"
    check_error "$code" "$body"
    feeds=$(printf '%s' "$body" | jq -r '.[].id')
    total_extracted=0
    total_errors=0
    for feed_id in $feeds; do
        r=$(api_post "/api/feeds/$feed_id/extract")
        parse_response "$r"
        if [ "$code" -lt 400 ] 2>/dev/null; then
            extracted=$(printf '%s' "$body" | jq -r '.extracted // 0')
            errs=$(printf '%s' "$body" | jq -r '.errors | length')
            total_extracted=$((total_extracted + extracted))
            total_errors=$((total_errors + errs))
        fi
    done
    if [ "$JSON_OUTPUT" = "1" ]; then
        jq -n --argjson e "$total_extracted" --argjson err "$total_errors" \
            '{articles_extracted: $e, errors_count: $err}'
    else
        printf 'Extract complete: articles_extracted=%s errors=%s\n' "$total_extracted" "$total_errors"
    fi
}

cmd_run() {
    all=0
    for arg in "$@"; do
        case "$arg" in
            --all) all=1 ;;
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_run; exit 0 ;;
        esac
    done

    if [ "$all" = "1" ]; then
        resp=$(api_post "/api/batch/process")
        parse_response "$resp"
        check_error "$code" "$body"
        if [ "$JSON_OUTPUT" = "1" ]; then
            printf '%s\n' "$body"
        else
            printf '%s\n' "$body" | jq -r '"Pipeline complete: feeds_parsed=\(.feeds_parsed) articles_discovered=\(.articles_discovered) articles_extracted=\(.articles_extracted) errors=\(.errors | length)"'
        fi
        return
    fi

    name=""
    for arg in "$@"; do
        case "$arg" in
            --all|--json|--help|-h) ;;
            *) name="$arg" ;;
        esac
    done
    [ -z "$name" ] && die "Missing website name or --all.\nRun 'feed-parser help run' for usage."
    id=$(resolve_name "$name")
    resp=$(api_post "/api/batch/process/$id")
    parse_response "$resp"
    check_error "$code" "$body"
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$body"
    else
        printf '%s\n' "$body" | jq -r '"Pipeline complete: feeds_parsed=\(.feeds_parsed) articles_discovered=\(.articles_discovered) articles_extracted=\(.articles_extracted) errors=\(.errors | length)"'
    fi
}

cmd_article() {
    if [ "$1" = "delete" ]; then
        shift
        for arg in "$@"; do
            case "$arg" in
                --json) JSON_OUTPUT=1 ;;
                --help|-h) usage_article; exit 0 ;;
            esac
        done
        art_id=""
        for arg in "$@"; do
            case "$arg" in
                --json|--help|-h) ;;
                *) art_id="$arg" ;;
            esac
        done
        [ -z "$art_id" ] && die "Missing article id.\nRun 'feed-parser help article' for usage."
        resp=$(api_delete "/api/articles/$art_id")
        parse_response "$resp"
        check_error "$code" "$body"
        printf 'Article %s deleted.\n' "$art_id"
        return
    fi

    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_article; exit 0 ;;
        esac
    done
    art_id=""
    for arg in "$@"; do
        case "$arg" in
            --json|--help|-h) ;;
            *) art_id="$arg" ;;
        esac
    done
    [ -z "$art_id" ] && die "Missing article id.\nRun 'feed-parser help article' for usage."
    resp=$(api_get "/api/articles/$art_id")
    parse_response "$resp"
    check_error "$code" "$body"
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$body"
    else
        printf '%s\n' "$body" | jq -r '"Article #\(.id)\n  title:   \(.title // "(none)")\n  url:     \(.url)\n  status:  \(.status)\n  author:  \(.author // "(none)")\n  published: \(.published_at // "(unknown)")"'
        has_text=$(printf '%s' "$body" | jq -r '.extracted_text != null')
        if [ "$has_text" = "true" ]; then
            printf '\n--- Extracted Text ---\n'
            printf '%s\n' "$body" | jq -r '.extracted_text' | head -n 30
        fi
    fi
}

cmd_status() {
    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_status; exit 0 ;;
        esac
    done
    resp=$(api_get "/status")
    parse_response "$resp"
    check_error "$code" "$body"
    if [ "$JSON_OUTPUT" = "1" ]; then
        printf '%s\n' "$body"
    else
        printf '%s\n' "$body" | jq -r '"Pipeline Status\n  websites: \(.total_websites)\n  feeds:    \(.total_feeds)\n  articles: \(.total_articles)\n    pending:   \(.articles_by_status.pending // 0)\n    extracted: \(.articles_by_status.extracted // 0)\n    downloaded:\(.articles_by_status.downloaded // 0)\n    failed:    \(.articles_by_status.failed // 0)"'
    fi
}

cmd_delete() {
    for arg in "$@"; do
        case "$arg" in
            --json) JSON_OUTPUT=1 ;;
            --help|-h) usage_delete; exit 0 ;;
        esac
    done
    name=""
    for arg in "$@"; do
        case "$arg" in
            --json|--help|-h) ;;
            *) name="$arg" ;;
        esac
    done
    [ -z "$name" ] && die "Missing website name.\nRun 'feed-parser help delete' for usage."
    id=$(resolve_name "$name")
    resp=$(api_delete "/api/websites/$id")
    parse_response "$resp"
    check_error "$code" "$body"
    printf 'Website "%s" (id=%s) deleted.\n' "$name" "$id"
}

# ── main dispatch ─────────────────────────────────────────────────────────────

# Strip global --json / --help before command dispatch
cmd=""
args=""
for arg in "$@"; do
    case "$arg" in
        --json) JSON_OUTPUT=1 ;;
        --help|-h) usage_main; exit 0 ;;
        *)
            if [ -z "$cmd" ]; then cmd="$arg"
            else args="$args $arg"
            fi
            ;;
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
    help)
        sub=$(printf '%s' "$args" | tr -d ' ')
        case "$sub" in
            add)      usage_add ;;
            list)     usage_list ;;
            discover) usage_discover ;;
            parse)    usage_parse ;;
            extract)  usage_extract ;;
            run)      usage_run ;;
            article)  usage_article ;;
            status)   usage_status ;;
            delete)   usage_delete ;;
            "")       usage_main ;;
            *)        die "Unknown command: $sub" ;;
        esac
        ;;
    "") usage_main; exit 0 ;;
    *)  die "Unknown command: $cmd\nRun 'feed-parser help' for usage." ;;
esac
