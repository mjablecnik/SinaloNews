# Requirements Document

## Introduction

An RSS feed discovery, parsing, and article extraction pipeline exposed as a REST API. The system accepts domains or URLs, discovers RSS feeds on those websites, parses feed entries using feedparser, downloads and extracts article content using Trafilatura, and stores both original and extracted data in PostgreSQL. Each processing phase is exposed as an independent API endpoint to allow debugging, re-running, and batch operations.

## Glossary

- **Pipeline**: The complete system encompassing feed discovery, parsing, downloading, extraction, and storage
- **Feed_Discovery_Service**: The component responsible for finding RSS feed URLs on a given website
- **Feed_Parser_Service**: The component responsible for parsing RSS/Atom feeds and extracting article entries
- **Article_Extractor_Service**: The component responsible for downloading article HTML and extracting text using Trafilatura
- **API_Server**: The FastAPI-based REST server exposing all pipeline operations as HTTP endpoints
- **Website**: A registered domain or URL that the user wants to monitor for RSS feeds
- **Feed**: An RSS or Atom feed URL discovered on a registered website
- **Article**: A single entry/item from a parsed feed, including its metadata and content
- **Batch_Processor**: The component that orchestrates parsing, downloading, extraction, and storing articles in bulk
- **CLI_Client**: A bash shell script (`feed-parser.sh`) that wraps API calls via curl and jq, allowing users to manage websites, feeds, and articles without using curl directly

## Requirements

### Requirement 1: Website Registration

**User Story:** As a user, I want to register websites by providing a domain or URL, so that the system can discover and track RSS feeds from those websites.

#### Acceptance Criteria

1. WHEN a valid URL or domain is submitted with a name, THE API_Server SHALL create a new website record in the database, automatically trigger feed discovery, and return the created resource with its ID and discovered feeds
2. WHEN a URL or domain that is already registered is submitted, THE API_Server SHALL return the existing website record without creating a duplicate
3. WHEN an invalid URL or domain is submitted, THE API_Server SHALL return a 422 validation error with a descriptive message
4. THE API_Server SHALL provide an endpoint to list all registered websites with pagination support
5. THE API_Server SHALL provide an endpoint to delete a registered website by ID

### Requirement 2: RSS Feed Discovery

**User Story:** As a user, I want the system to automatically discover RSS/Atom feeds on registered websites, so that I don't have to manually find feed URLs.

#### Acceptance Criteria

1. WHEN feed discovery is triggered for a website, THE Feed_Discovery_Service SHALL scan the website's HTML for RSS/Atom feed links in `<link>` tags
2. WHEN feed discovery is triggered for a website, THE Feed_Discovery_Service SHALL check common feed URL patterns (e.g., `/feed`, `/rss`, `/atom.xml`, `/feed.xml`)
3. WHEN one or more feeds are discovered, THE Feed_Discovery_Service SHALL store each feed URL associated with the website in the database
4. WHEN no feeds are discovered, THE Feed_Discovery_Service SHALL update the website record to indicate that no feeds were found
5. IF a network error occurs during discovery, THEN THE Feed_Discovery_Service SHALL return an error response with the failure reason and not modify existing feed records
6. THE API_Server SHALL provide a dedicated endpoint to trigger feed discovery for a specific website by ID
7. THE API_Server SHALL provide an endpoint to list all discovered feeds for a specific website

### Requirement 3: Feed Parsing

**User Story:** As a user, I want to parse discovered feeds to extract the latest article entries, so that I can track new content from monitored websites.

#### Acceptance Criteria

1. WHEN feed parsing is triggered for a feed, THE Feed_Parser_Service SHALL use feedparser to retrieve and parse the feed
2. WHEN feed parsing succeeds, THE Feed_Parser_Service SHALL extract article metadata including title, link, published date, author, and summary from each entry
3. WHEN a new article entry is found that does not already exist in the database, THE Feed_Parser_Service SHALL create a new article record with feedparser metadata
4. WHEN an article entry already exists in the database (matched by link URL), THE Feed_Parser_Service SHALL skip the duplicate without overwriting existing data
5. IF the feed URL is unreachable or returns invalid content, THEN THE Feed_Parser_Service SHALL return an error response with the failure details
6. THE API_Server SHALL provide an endpoint to trigger parsing for a single feed by ID
7. THE API_Server SHALL provide an endpoint to trigger parsing for all feeds of a specific website

### Requirement 4: Article Download and Extraction

**User Story:** As a user, I want articles to be downloaded and processed using Trafilatura, so that I have both the original HTML and extracted text for further processing.

#### Acceptance Criteria

1. WHEN article extraction is triggered for an article, THE Article_Extractor_Service SHALL download the full HTML content from the article's URL
2. WHEN HTML content is successfully downloaded, THE Article_Extractor_Service SHALL store the original HTML in the article record
3. WHEN HTML content is successfully downloaded, THE Article_Extractor_Service SHALL extract text using Trafilatura and store it in the article record
4. WHEN extraction is complete, THE Article_Extractor_Service SHALL update the article status to indicate successful processing
5. IF the article URL is unreachable, THEN THE Article_Extractor_Service SHALL update the article status to indicate a download failure with the error message
6. IF Trafilatura fails to extract content, THEN THE Article_Extractor_Service SHALL store the original HTML and update the article status to indicate an extraction failure
7. THE API_Server SHALL provide an endpoint to trigger extraction for a single article by ID and return the extracted content
8. THE API_Server SHALL provide an endpoint to trigger batch extraction for all unprocessed articles of a specific feed

### Requirement 5: Batch Processing

**User Story:** As a user, I want to run the full pipeline (parse feeds, download articles, extract content) as a single batch operation, so that I can process everything in one step.

#### Acceptance Criteria

1. WHEN batch processing is triggered for a website, THE Batch_Processor SHALL execute feed parsing for all feeds of that website, then download and extract all newly discovered articles
2. WHEN batch processing is triggered without specifying a website, THE Batch_Processor SHALL process all registered websites
3. THE Batch_Processor SHALL report a summary including counts of feeds parsed, articles discovered, articles extracted, and errors encountered
4. IF any individual article fails during batch processing, THEN THE Batch_Processor SHALL continue processing remaining articles and include the failure in the summary
5. THE API_Server SHALL provide an endpoint to trigger batch processing for a specific website or all websites

### Requirement 6: Database Schema

**User Story:** As a user, I want a well-structured database that stores all pipeline data with both original and extracted content, so that I can debug extraction issues and use the data for further processing.

#### Acceptance Criteria

1. THE Pipeline SHALL store website records with fields: id, name, url, domain, created_at, updated_at, last_discovery_at, discovery_status
2. THE Pipeline SHALL store feed records with fields: id, website_id (foreign key), feed_url, title, feed_type (RSS/Atom), created_at, last_parsed_at
3. THE Pipeline SHALL store article records with fields: id, feed_id (foreign key), url, title, author, published_at, summary, original_html, extracted_text, status, feedparser_raw_entry (JSON), created_at, updated_at
4. THE Pipeline SHALL use appropriate indexes on url fields and foreign keys to ensure query performance
5. THE Pipeline SHALL enforce unique constraints on website URL, website name, feed URL per website, and article URL per feed to prevent duplicates

### Requirement 7: Article Retrieval

**User Story:** As a user, I want to retrieve articles with their original and extracted content, so that I can inspect and debug the extraction results.

#### Acceptance Criteria

1. THE API_Server SHALL provide an endpoint to retrieve a single article by ID including all stored fields
2. THE API_Server SHALL provide an endpoint to delete a single article by ID
3. THE API_Server SHALL provide an endpoint to list articles for a specific feed with pagination and filtering by status
4. THE API_Server SHALL provide an endpoint to list articles for a specific website (across all its feeds) with pagination and filtering by status
5. WHEN listing articles, THE API_Server SHALL support filtering by processing status (pending, downloaded, extracted, failed)

### Requirement 8: Health and Status

**User Story:** As a user, I want health and status endpoints, so that I can monitor the service and verify it is running correctly.

#### Acceptance Criteria

1. THE API_Server SHALL provide a health check endpoint that returns HTTP 200 when the service is operational
2. WHEN the database connection is unavailable, THE API_Server SHALL return HTTP 503 from the health check endpoint
3. THE API_Server SHALL provide a status endpoint that returns pipeline statistics including total websites, feeds, articles, and articles by processing status

### Requirement 9: Error Handling and Logging

**User Story:** As a user, I want consistent error handling and structured logging, so that I can diagnose issues when pipeline steps fail.

#### Acceptance Criteria

1. WHEN any API endpoint encounters an unhandled error, THE API_Server SHALL return a JSON error response with a consistent structure including error code, message, and request ID
2. THE Pipeline SHALL log all operations with structured logging including timestamp, level, component name, and relevant context (website_id, feed_id, article_id)
3. IF a request includes invalid parameters, THEN THE API_Server SHALL return HTTP 422 with field-level validation errors

### Requirement 10: Rate Limiting and Politeness

**User Story:** As a user, I want the system to respect target websites by implementing rate limiting and polite crawling, so that the service does not get blocked or cause issues for target servers.

#### Acceptance Criteria

1. WHEN downloading content from external websites, THE Pipeline SHALL enforce a configurable delay between requests to the same domain (default: 1 second)
2. WHEN downloading content, THE Pipeline SHALL send a configurable User-Agent header identifying the service
3. WHEN a target server returns HTTP 429 (Too Many Requests), THE Pipeline SHALL respect the Retry-After header and delay subsequent requests accordingly
4. THE Pipeline SHALL enforce a configurable timeout for all external HTTP requests (default: 30 seconds)

### Requirement 11: Configuration

**User Story:** As a user, I want all service configuration to be managed through environment variables, so that I can easily adjust settings for different environments.

#### Acceptance Criteria

1. THE Pipeline SHALL read database connection parameters from environment variables (DATABASE_URL)
2. THE Pipeline SHALL read HTTP server configuration from environment variables (APP_HOST, APP_PORT)
3. THE Pipeline SHALL read crawling configuration from environment variables (REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT_SECONDS, USER_AGENT)
4. THE Pipeline SHALL provide sensible defaults for all optional configuration values
5. IF a required environment variable is missing, THEN THE Pipeline SHALL fail to start with a clear error message indicating which variable is missing

### Requirement 12: CLI Client

**User Story:** As a user, I want a command-line tool that wraps the API, so that I can manage websites, feeds, and articles from the terminal without writing curl commands.

#### Acceptance Criteria

1. THE CLI_Client SHALL be implemented as a POSIX-compatible shell script (`feed-parser.sh`) using curl for HTTP requests and jq for JSON formatting, invokable as `feed-parser` via symlink or PATH
2. THE CLI_Client SHALL support `feed-parser add <name> <url>` with positional arguments to register a new website, and alternatively accept named flags `feed-parser add --name=<name> --source=<url>`
3. WHEN the provided URL has no protocol prefix, THE CLI_Client SHALL automatically prepend `https://`
3. THE CLI_Client SHALL support `feed-parser list` to display all registered websites with their IDs, names, and discovery status
4. THE CLI_Client SHALL support `feed-parser list articles <name>` to display all articles for a given website name, formatted as a readable table
5. THE CLI_Client SHALL support `feed-parser discover <name>` to trigger RSS feed discovery for a website by name
6. THE CLI_Client SHALL support `feed-parser parse <name>` to trigger feed parsing for all feeds of a website by name
7. THE CLI_Client SHALL support `feed-parser parse --all` to trigger feed parsing for all registered websites
8. THE CLI_Client SHALL support `feed-parser extract <name>` to trigger article download and extraction for all unprocessed articles of a website
9. THE CLI_Client SHALL support `feed-parser extract --all` to trigger extraction for all unprocessed articles across all websites
10. THE CLI_Client SHALL support `feed-parser run <name>` to execute the pipeline (parse, extract) for a website in one command
11. THE CLI_Client SHALL support `feed-parser run --all` to execute the full pipeline for all registered websites
12. THE CLI_Client SHALL support `feed-parser article <id>` to display a single article's details including extracted text and status
13. THE CLI_Client SHALL support `feed-parser article delete <id>` to delete a single article by ID
14. THE CLI_Client SHALL support `feed-parser status` to display pipeline statistics (total websites, feeds, articles by status)
14. THE CLI_Client SHALL support `feed-parser delete <name>` to remove a registered website by name
15. THE CLI_Client SHALL read the API base URL from the environment variable `FEED_PARSER_API_URL` with a default of `http://localhost:8000`
16. THE CLI_Client SHALL display errors from the API in a human-readable format with the HTTP status code
17. THE CLI_Client SHALL support `--json` flag on all commands to output raw JSON instead of formatted text
18. THE CLI_Client SHALL support `feed-parser help` and `feed-parser --help` to display a summary of all available commands with brief descriptions
19. THE CLI_Client SHALL support `feed-parser help <command>` and `feed-parser <command> --help` to display detailed usage, flags, and examples for a specific command

### Requirement 13: API Documentation

**User Story:** As a user, I want comprehensive API documentation with examples, so that I can understand and use all available endpoints.

#### Acceptance Criteria

1. THE API_Server SHALL expose an OpenAPI/Swagger UI at `/docs` for interactive API exploration
2. THE Pipeline SHALL include a Markdown documentation file listing all endpoints with request/response examples
3. THE API_Server SHALL include descriptive summaries and response schemas for all endpoints in the OpenAPI specification

