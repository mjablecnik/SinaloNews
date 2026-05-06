# Requirements Document

## Introduction

The Article Classifier is a FastAPI service that uses LLM-powered AI (LangGraph/LangChain + OpenRouter + LangSmith) to classify, tag, score, and summarize articles stored in the shared PostgreSQL database. It reads unprocessed articles from the existing `articles` table (owned by the rss-feed service), generates hierarchical topic tags, assigns a content type classification, computes a personal importance score (calibrated for a Czech user), and produces a brief summary. Results are stored in dedicated tables and exposed via a REST API for filtering and retrieval.

## Glossary

- **Classifier_Service**: The article-classifier FastAPI application responsible for orchestrating LLM-based classification of articles.
- **Classification_Pipeline**: The LangGraph-based AI pipeline that processes a single article through tagging, content typing, scoring, and summarization steps.
- **Article**: A record in the shared `articles` table containing extracted text content from an RSS feed item.
- **Tag**: A hierarchical label consisting of a main category and a subcategory that describes the topic of an article.
- **Content_Type**: An enumerated classification indicating the quality and nature of an article's content.
- **Importance_Score**: An integer value from 0 to 10 representing how relevant and valuable an article is to the target user.
- **Classification_Result**: The combined output of the pipeline for a single article: tags, content type, importance score, and summary.
- **Unprocessed_Article**: An article in the `articles` table that has `extracted_text` present and no corresponding classification result in the classifier's tables.

## Requirements

### Requirement 1: Fetch Unprocessed Articles

**User Story:** As a system operator, I want the classifier to identify and fetch articles that have not yet been classified, so that new content is continuously processed without duplication.

#### Acceptance Criteria

1. WHEN the classification process is triggered, THE Classifier_Service SHALL query the `articles` table for articles that have `extracted_text` not null and no corresponding record in the `classification_results` table.
2. THE Classifier_Service SHALL process unprocessed articles in batches of a configurable size (default 20).
3. THE Classifier_Service SHALL skip articles where `extracted_text` is empty or null.
4. IF a database connection error occurs during article fetching, THEN THE Classifier_Service SHALL log the error and retry up to 3 times with exponential backoff.
5. THE Classifier_Service SHALL track processing status to prevent concurrent classification of the same article.

### Requirement 2: Generate Hierarchical Tags

**User Story:** As a news reader, I want articles tagged with hierarchical topic labels, so that I can browse and filter content by subject area.

#### Acceptance Criteria

1. WHEN an article is processed, THE Classification_Pipeline SHALL generate one or more tags, each consisting of a main category and a subcategory.
2. THE Classification_Pipeline SHALL include the full list of existing tags in the LLM prompt so the model prioritizes matching existing tags.
3. THE Classification_Pipeline SHALL use the following predefined main categories and subcategories as the initial seed:
   - Politics: Czech, European, Global, USA, Diplomacy
   - Economy: Finance, Markets, Business, Law, Crypto, Jobs
   - Technology: Software, Hardware, AI, Cybersecurity, Cloud, Startups
   - Science: Research, Space, Medicine, Energy, Environment
   - Security: Military, Conflict, Terrorism, Crime, Defense
   - Society: Culture, Education, Health, Sports, Media
   - World: Disasters, Migration, Humanitarian, Climate
4. THE Classifier_Service SHALL store tags in a single `tags` table with a self-referencing `parent_id` column (NULL for main categories, FK to parent for subcategories) and an `article_tags` association table.
5. WHEN an article covers multiple topics, THE Classification_Pipeline SHALL assign all applicable tags (minimum 1, maximum 5 per article).
6. THE Classification_Pipeline SHALL treat main categories as fixed — the LLM SHALL NOT create new main categories, only new subcategories under existing categories.
7. IF the LLM returns a subcategory not in the existing set, THEN THE Classification_Pipeline SHALL perform a deduplication check (via LLM) comparing the new subcategory against existing subcategories within the same category to determine if it is a synonym or duplicate.
8. IF the deduplication check identifies the new subcategory as a duplicate of an existing one, THEN THE Classification_Pipeline SHALL map the article to the existing tag instead.
9. IF the deduplication check confirms the subcategory is genuinely new, THEN THE Classification_Pipeline SHALL create the new subcategory in the database under the appropriate main category and assign it to the article.

### Requirement 3: Classify Content Type

**User Story:** As a news reader, I want articles classified by content quality, so that I can filter out conspiracy theories, clickbait, and worthless content from genuinely valuable information.

#### Acceptance Criteria

1. WHEN an article is processed, THE Classification_Pipeline SHALL assign exactly one content type from the following enum:
   - CONSPIRACY_THEORY: Content promoting unfounded conspiracy theories or misinformation
   - CLICKBAIT: Sensationalized content with misleading headlines designed to generate clicks
   - NO_USEFUL_CONTENT: Content with no informational value (ads, spam, broken content, satire)
   - OPINION_EDITORIAL: Subjective opinion pieces, commentaries, columns, or reviews representing the author's personal viewpoint rather than factual reporting
   - BREAKING_NEWS: Hard news with immediate impact (war, natural disasters, government collapse, major security events)
   - GENERAL_VALUABLE_CONTENT: Informative content of general interest
   - UNIVERSAL_RELEVANT_CONTENT: High-quality content of broad relevance and importance
2. THE Classification_Pipeline SHALL base the content type decision on the article's extracted text, title, and summary.
3. IF the LLM returns a value not matching the defined enum, THEN THE Classification_Pipeline SHALL default to GENERAL_VALUABLE_CONTENT and log a warning.

### Requirement 4: Assign Importance Score

**User Story:** As a Czech news reader, I want articles scored by personal relevance, so that I can prioritize reading the most important content first.

#### Acceptance Criteria

1. WHEN an article is processed, THE Classification_Pipeline SHALL assign an integer importance score from 0 to 10.
2. THE Classification_Pipeline SHALL apply the following scoring criteria:
   - Score 9-10: Information that directly affects the Czech Republic, Czech citizens, or the user's daily life (legislation changes, major domestic events)
   - Score 7-8: Events in Europe or globally that have direct consequences for Czech Republic (EU regulations, trade agreements, security threats)
   - Score 5-6: Significant global events of general importance without direct Czech impact
   - Score 3-4: Notable events with limited personal relevance (foreign political scandals, distant regional conflicts)
   - Score 1-2: Minor events with minimal informational value
   - Score 0: Content with no informational value whatsoever
3. THE Classification_Pipeline SHALL increase the score for articles about topics that could affect voting preferences or personal financial decisions.
4. THE Classification_Pipeline SHALL decrease the score for accidents or incidents abroad that do not directly affect Czech citizens.
5. IF the LLM returns a score outside the 0-10 range, THEN THE Classification_Pipeline SHALL clamp the value to the nearest valid boundary (0 or 10).

### Requirement 5: Generate Article Summary

**User Story:** As a news reader, I want a brief summary of each article, so that I can quickly understand the content without reading the full text.

#### Acceptance Criteria

1. WHEN an article is processed, THE Classification_Pipeline SHALL generate a summary of the article in Czech language regardless of the original article language.
2. THE Classification_Pipeline SHALL produce a concise summary of approximately one paragraph, formatted in Markdown for easy rendering in a reader application.
3. THE Classification_Pipeline SHALL capture ALL key facts, conclusions, names, numbers, dates, and actionable information from the article so that reading the summary is sufficient to understand the article without reading the original.
4. THE Classification_Pipeline MAY use Markdown formatting (bold, italic, bullet points) in the summary when it improves readability.
5. IF the article's extracted text is shorter than 100 characters, THEN THE Classification_Pipeline SHALL use the extracted text as the summary without LLM processing.

### Requirement 6: REST API for Classified Articles

**User Story:** As an API consumer, I want to query classified articles with filters and sorting, so that I can retrieve relevant content efficiently.

#### Acceptance Criteria

1. THE Classifier_Service SHALL expose a `GET /api/articles` endpoint that returns paginated classified articles.
2. THE Classifier_Service SHALL support filtering by tag main category via query parameter `category`.
3. THE Classifier_Service SHALL support filtering by tag subcategory via query parameter `subcategory`.
4. THE Classifier_Service SHALL support filtering by content type via query parameter `content_type`.
5. THE Classifier_Service SHALL support filtering by minimum importance score via query parameter `min_score`.
6. THE Classifier_Service SHALL support filtering by date range via query parameters `date_from` and `date_to`.
7. THE Classifier_Service SHALL support sorting by `importance_score`, `published_at`, or `classified_at` via query parameter `sort_by` (default: `classified_at`).
8. THE Classifier_Service SHALL support sort direction via query parameter `sort_order` with values `asc` or `desc` (default: `desc`).
9. THE Classifier_Service SHALL return paginated results with `page` and `size` query parameters (default page=1, size=20, maximum size=100).
10. WHEN filters are combined, THE Classifier_Service SHALL apply all filters with AND logic.
11. THE Classifier_Service SHALL include in each response item: article id, title, url, author, published_at, tags, content_type, importance_score, summary, and classified_at.

### Requirement 7: Classification Trigger API

**User Story:** As a system operator, I want to trigger the classification process via API, so that I can run it on demand or schedule it externally.

#### Acceptance Criteria

1. THE Classifier_Service SHALL expose a `POST /api/classify` endpoint that triggers classification of unprocessed articles.
2. WHEN the classify endpoint is called, THE Classifier_Service SHALL return immediately with a response containing the number of articles queued for processing.
3. THE Classifier_Service SHALL process articles asynchronously after returning the trigger response.
4. THE Classifier_Service SHALL expose a `GET /api/classify/status` endpoint that returns the current processing state (idle, processing, count of pending articles, count of classified articles).
5. IF classification is already in progress, THEN THE Classifier_Service SHALL reject a new trigger request with HTTP 409 and a descriptive message.

### Requirement 8: LLM Pipeline Efficiency

**User Story:** As a system operator, I want the classification pipeline to be cost-efficient, so that LLM API costs remain manageable.

#### Acceptance Criteria

1. THE Classification_Pipeline SHALL combine tag generation, content type classification, importance scoring, and summary generation into a single LLM call per article.
2. THE Classification_Pipeline SHALL use structured output (JSON) to extract all classification fields from one LLM response with the following structure:
   ```json
   {
     "tags": [{"category": "...", "subcategory": "..."}],
     "content_type": "OPINION_EDITORIAL",
     "score": 7,
     "reason": "Explanation of why this score and content type were assigned",
     "summary": "Brief summary of the article"
   }
   ```
3. THE Classification_Pipeline SHALL require the `reason` field in English explaining why the given score and content type were chosen, serving as a debug/audit trail.
4. THE Classifier_Service SHALL persist all JSON response fields (including `reason`) in the classification results table.
5. IF an LLM API call fails with a rate limit error (HTTP 429), THEN THE Classification_Pipeline SHALL retry after a configurable delay (default 5 seconds) up to 3 times.
6. IF an LLM API call fails with a non-retryable error, THEN THE Classification_Pipeline SHALL log the error, mark the article as failed, and continue processing the next article.
7. THE Classifier_Service SHALL record the LLM model used and token count for each classification in the result metadata.

### Requirement 9: Health and Observability

**User Story:** As a system operator, I want health checks and observability, so that I can monitor the service and diagnose issues.

#### Acceptance Criteria

1. THE Classifier_Service SHALL expose a `GET /health` endpoint that reports the status of the database connection and LLM API availability.
2. THE Classifier_Service SHALL log all classification operations using structlog with structured JSON output.
3. THE Classifier_Service SHALL integrate with LangSmith for tracing all LLM calls in the classification pipeline.
4. THE Classifier_Service SHALL log the processing time, token usage, and result summary for each classified article.
5. IF the database is unreachable, THEN THE Classifier_Service SHALL return HTTP 503 from the health endpoint with status "unavailable".

### Requirement 10: Configuration

**User Story:** As a developer, I want all configuration externalized via environment variables, so that the service can be deployed across environments without code changes.

#### Acceptance Criteria

1. THE Classifier_Service SHALL read all configuration from environment variables using pydantic-settings.
2. THE Classifier_Service SHALL require the following environment variables: `DATABASE_URL`, `OPENROUTER_API_KEY`.
3. THE Classifier_Service SHALL support optional configuration for: `APP_PORT` (default 8002), `LLM_MODEL` (default "openai/gpt-4o-mini"), `BATCH_SIZE` (default 20), `LLM_RETRY_DELAY_SECONDS` (default 5), `LLM_MAX_RETRIES` (default 3), `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` (default "sinalo-classifier"), `LANGSMITH_TRACING` (default "true").
4. THE Classifier_Service SHALL provide a `.env.example` file documenting all environment variables with placeholder values and comments.
