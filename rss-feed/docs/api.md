# RSS Feed Pipeline — API Reference

Base URL: `http://localhost:8000` (configurable via `FEED_PARSER_API_URL`)

Interactive docs (Swagger UI): `/docs`

---

## Websites

### POST /api/websites
Register a new website.

**Request body**
```json
{ "name": "Hacker News", "url": "https://news.ycombinator.com" }
```

**Response 201** — created
```json
{
  "id": 1,
  "name": "Hacker News",
  "url": "https://news.ycombinator.com",
  "domain": "news.ycombinator.com",
  "created_at": "2024-01-15T10:00:00",
  "discovery_status": "pending"
}
```

**Response 200** — already exists (same record returned)

---

### GET /api/websites
List all registered websites (paginated).

**Query params**: `page` (default 1), `size` (default 20, max 100)

**Response 200**
```json
{
  "items": [ { "id": 1, "name": "Hacker News", ... } ],
  "total": 1,
  "page": 1,
  "size": 20,
  "pages": 1
}
```

---

### GET /api/websites/{id}
Get a single website by ID.

**Response 200** — `WebsiteResponse`
**Response 404** — not found

---

### DELETE /api/websites/{id}
Delete a website and all its feeds and articles.

**Response 204** — no content
**Response 404** — not found

---

### POST /api/websites/{id}/discover
Trigger RSS/Atom feed discovery for a website.

**Response 200**
```json
{
  "website_id": 1,
  "feeds_found": 2,
  "feeds": [
    { "id": 1, "website_id": 1, "feed_url": "https://news.ycombinator.com/rss", "title": null, "feed_type": "rss", "last_parsed_at": null }
  ]
}
```

---

### GET /api/websites/{id}/feeds
List all feeds discovered for a website.

**Response 200** — `list[FeedResponse]`

---

### GET /api/websites/{id}/articles
List all articles across all feeds for a website (paginated, filterable).

**Query params**: `page`, `size`, `status` (pending | downloaded | extracted | failed)

**Response 200** — `PaginatedResponse[ArticleResponse]`

---

## Feeds

### POST /api/feeds/{id}/parse
Parse a single feed and create article records for new entries.

**Response 200**
```json
{ "feeds_parsed": 1, "articles_discovered": 15, "errors": [] }
```

---

### POST /api/websites/{id}/parse
Parse all feeds for a website.

**Response 200** — same as above, aggregated

---

## Articles

### GET /api/articles/{id}
Get a single article with all fields including extracted text.

**Response 200**
```json
{
  "id": 42,
  "feed_id": 1,
  "url": "https://example.com/article",
  "title": "Example Article",
  "author": "Alice",
  "published_at": "2024-01-14T12:00:00",
  "status": "extracted",
  "summary": "...",
  "original_html": "<html>...</html>",
  "extracted_text": "Article body text...",
  "feedparser_raw_entry": { ... }
}
```

**Response 404** — not found

---

### DELETE /api/articles/{id}
Delete an article.

**Response 204** — no content
**Response 404** — not found

---

### GET /api/feeds/{id}/articles
List articles for a feed (paginated, filterable by status).

**Query params**: `page`, `size`, `status`

**Response 200** — `PaginatedResponse[ArticleResponse]`

---

### POST /api/articles/{id}/extract
Download and extract a single article. Returns the updated article.

**Response 200** — `ArticleDetailResponse`

---

### POST /api/feeds/{id}/extract
Extract all unprocessed articles for a feed.

**Response 200**
```json
{ "articles_extracted": 10, "errors": [] }
```

---

## Batch

### POST /api/batch/process
Run the full pipeline (parse all feeds + extract all new articles) for every registered website.

**Response 200**
```json
{
  "feeds_parsed": 5,
  "articles_discovered": 42,
  "articles_extracted": 38,
  "errors": ["Feed 3: connection timeout"]
}
```

---

### POST /api/batch/process/{website_id}
Run the full pipeline for a single website.

**Response 200** — same structure as above

---

## Health & Status

### GET /health
Health check. Returns 200 when the database is reachable, 503 otherwise.

**Response 200**
```json
{ "status": "ok" }
```

---

### GET /status
Pipeline statistics.

**Response 200**
```json
{
  "total_websites": 3,
  "total_feeds": 8,
  "total_articles": 1200,
  "articles_by_status": {
    "pending": 100,
    "downloaded": 50,
    "extracted": 1000,
    "failed": 50
  }
}
```

---

## Error Responses

All errors return a consistent JSON structure:

```json
{
  "error": "not_found",
  "message": "Website not found",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "details": null
}
```

| Scenario | Status | `error` |
|---|---|---|
| Invalid request body / params | 422 | `validation_error` |
| Resource not found | 404 | `not_found` |
| Network error during crawling | 502 | `network_error` |
| Feed parsing failure | 502 | `parse_error` |
| Database unavailable | 503 | `service_unavailable` |
| Unhandled exception | 500 | `internal_error` |
