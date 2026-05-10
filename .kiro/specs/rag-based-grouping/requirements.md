# Requirements Document

## Introduction

The RAG-Based Grouping feature replaces the current LLM-based article clustering mechanism with a vector similarity approach using Qdrant. Instead of sending batches of articles to an LLM for clustering, each article is embedded as a whole document and stored in a dedicated Qdrant collection (`article_full`). When grouping is triggered, each unprocessed article is compared against existing articles in the collection using cosine similarity. Articles exceeding a configurable similarity threshold are grouped together, either joining an existing group or forming a new one. This approach eliminates the expensive LLM clustering calls, reduces latency, and provides deterministic, threshold-based grouping decisions.

The existing database schema (`article_groups`, `article_group_members` tables), feed endpoint, group detail endpoint, and reader app display remain unchanged. Only the mechanism of HOW articles get grouped changes — from LLM-based clustering to RAG-based similarity matching.

## Glossary

- **Grouping_Service**: The component within the article-classifier service responsible for orchestrating the RAG-based similarity grouping of articles.
- **Full_Article_Collection**: A Qdrant vector collection (`article_full`) that stores one embedding per article, representing the full `extracted_text` as a single vector.
- **Embedding_Client**: The HTTP client that calls the OpenRouter embeddings API (model: `openai/text-embedding-3-small`) to generate vector representations of article text.
- **Similarity_Threshold**: A configurable floating-point value (0.0–1.0) representing the minimum cosine similarity score required for two articles to be considered similar enough to group together.
- **Article_Group**: A collection of two or more articles that have been determined to cover the same topic based on vector similarity exceeding the threshold.
- **Standalone_Article**: An article whose similarity to all other articles in the collection falls below the threshold, remaining ungrouped.
- **Group_Detail_Pipeline**: The LLM-based pipeline that generates a Czech-language title, summary, and combined detail article for each group (retained from the existing system, triggered separately via regenerate endpoint).
- **Needs_Regeneration**: A boolean flag on an Article_Group indicating that the group's detail text (title, summary, detail) is stale and needs to be regenerated via the regenerate endpoint.
- **Article_API**: The article-classifier service's REST API that provides classified article data and group data.
- **Reader_App**: The SvelteKit web application that displays articles and article groups to the user.

## Requirements

### Requirement 1: Full-Article Qdrant Collection

**User Story:** As a system operator, I want articles stored as whole-document embeddings in a dedicated Qdrant collection, so that similarity search can compare full article content rather than chunks.

#### Acceptance Criteria

1. THE Grouping_Service SHALL create and maintain a Qdrant collection named according to the `QDRANT_FULL_ARTICLE_COLLECTION` configuration (default: `article_full`) with cosine distance metric.
2. THE Grouping_Service SHALL ensure the Full_Article_Collection exists before performing any indexing or search operations, creating the collection if it does not exist.
3. THE Grouping_Service SHALL store exactly one vector per article in the Full_Article_Collection, representing the full `extracted_text` field embedded as a single document.
4. THE Grouping_Service SHALL store the following payload metadata with each vector: `article_id`, `article_title`, `published_at`, and `indexed_at`.
5. THE Grouping_Service SHALL use a deterministic point ID derived from the article ID, so that re-indexing the same article overwrites the existing point rather than creating duplicates.
6. IF an article has empty or missing `extracted_text`, THEN THE Grouping_Service SHALL skip that article during indexing and log a warning.

### Requirement 2: Article Embedding and Indexing

**User Story:** As a system operator, I want new articles automatically embedded and indexed into the full-article collection, so that they are available for similarity comparison.

#### Acceptance Criteria

1. WHEN the grouping process is triggered, THE Grouping_Service SHALL identify articles that have been classified but not yet indexed in the Full_Article_Collection.
2. THE Grouping_Service SHALL embed each unindexed article's full `extracted_text` using the Embedding_Client (model: `openai/text-embedding-3-small` via OpenRouter API).
3. THE Grouping_Service SHALL upsert the resulting embedding vector and metadata into the Full_Article_Collection.
4. THE Grouping_Service SHALL track which articles have been indexed in the Full_Article_Collection to avoid redundant embedding API calls on subsequent runs.
5. IF the Embedding_Client returns an error for a specific article, THEN THE Grouping_Service SHALL log the error, skip that article, and continue processing remaining articles.
6. THE Grouping_Service SHALL process articles for indexing in batches to manage memory and API rate limits.

### Requirement 3: RAG-Based Similarity Grouping

**User Story:** As a reader, I want similar articles grouped together based on content similarity, so that I see consolidated information instead of duplicates.

#### Acceptance Criteria

1. WHEN the grouping process is triggered, THE Grouping_Service SHALL process each unprocessed (not yet grouped and newly indexed) article by querying the Full_Article_Collection for the most similar article.
2. THE Grouping_Service SHALL exclude the article itself from its own similarity search results.
3. WHEN the highest similarity score exceeds the Similarity_Threshold, THE Grouping_Service SHALL check whether the most similar article already belongs to an Article_Group.
4. IF the most similar article belongs to an existing Article_Group, THEN THE Grouping_Service SHALL add the current article to that existing group.
5. IF the most similar article does not belong to any Article_Group, THEN THE Grouping_Service SHALL create a new Article_Group containing both articles.
6. IF the highest similarity score is below the Similarity_Threshold, THEN THE Grouping_Service SHALL leave the article as a Standalone_Article.
7. THE Grouping_Service SHALL process articles sequentially so that groups formed by earlier articles are available for later articles to join.
8. THE Grouping_Service SHALL respect the existing unique constraint on `article_id` in `article_group_members` — each article belongs to at most one group.
9. WHEN a new article is added to an existing Article_Group, THE Grouping_Service SHALL update the group's `grouped_date` to the `published_at` date of the most recent member article in the group.
10. WHEN a new article is added to an existing Article_Group OR a new Article_Group is created, THE Grouping_Service SHALL set a `needs_regeneration` flag (boolean) on the group to indicate that the group's detail text needs to be regenerated.

### Requirement 4: Group Detail Regeneration

**User Story:** As a reader, I want each article group to have a title, summary, and combined detail article that stays up-to-date as new articles join the group, so that I can browse and read consolidated content.

#### Acceptance Criteria

1. THE Article_API SHALL expose a `POST /api/groups/regenerate` endpoint that triggers detail regeneration for all groups with `needs_regeneration = true`.
2. WHEN the regenerate endpoint is called, THE Group_Detail_Pipeline SHALL generate a title, summary, and detail for each flagged group using the full `extracted_text` of all member articles.
3. THE Group_Detail_Pipeline SHALL generate all output (title, summary, detail) in Czech language.
4. THE Group_Detail_Pipeline SHALL generate the summary as a concise one-paragraph text suitable for card display.
5. THE Group_Detail_Pipeline SHALL generate the detail as a longer combined article (approximately 2-5 paragraphs) in Czech Markdown, synthesizing key facts from all member articles.
6. WHEN detail regeneration succeeds for a group, THE Grouping_Service SHALL clear the `needs_regeneration` flag on that group.
7. IF the Group_Detail_Pipeline fails for a specific group, THEN THE Grouping_Service SHALL log the error and leave the `needs_regeneration` flag set so it can be retried later.
8. THE regenerate endpoint SHALL process synchronously and return the number of groups regenerated.
9. THE grouping process (similarity matching) SHALL NOT call the Group_Detail_Pipeline directly — it only sets the `needs_regeneration` flag. Detail generation is triggered separately via the regenerate endpoint.

### Requirement 5: Configurable Similarity Threshold

**User Story:** As a system operator, I want the similarity threshold configurable via environment variable, so that grouping sensitivity can be tuned without code changes.

#### Acceptance Criteria

1. THE Grouping_Service SHALL support a `GROUPING_SIMILARITY_THRESHOLD` environment variable specifying the minimum cosine similarity score for grouping (default: 0.75).
2. THE Grouping_Service SHALL validate that the threshold value is between 0.0 and 1.0 (inclusive).
3. WHEN the threshold is set to a higher value, THE Grouping_Service SHALL produce fewer and tighter groups (only very similar articles grouped).
4. WHEN the threshold is set to a lower value, THE Grouping_Service SHALL produce more and broader groups (moderately similar articles grouped).

### Requirement 6: Configuration

**User Story:** As a developer, I want all RAG-based grouping configuration externalized via environment variables, so that behavior can be tuned without code changes.

#### Acceptance Criteria

1. THE Grouping_Service SHALL support a `QDRANT_URL` environment variable for the Qdrant server connection (default: `http://localhost:6333`).
2. THE Grouping_Service SHALL support a `QDRANT_API_KEY` environment variable for Qdrant authentication (optional, default: None).
3. THE Grouping_Service SHALL support a `QDRANT_FULL_ARTICLE_COLLECTION` environment variable for the collection name (default: `article_full`).
4. THE Grouping_Service SHALL support an `EMBEDDING_MODEL` environment variable for the embedding model (default: `openai/text-embedding-3-small`).
5. THE Grouping_Service SHALL support an `EMBEDDING_API_URL` environment variable for the embedding API endpoint (default: `https://openrouter.ai/api/v1`).
6. THE Grouping_Service SHALL reuse the existing `OPENROUTER_API_KEY` for embedding API authentication.
7. THE Grouping_Service SHALL retain the existing `GROUPING_LLM_MODEL` configuration for the group detail generation LLM calls.
8. THE Grouping_Service SHALL retain the existing `GROUPING_MIN_ARTICLES` configuration — categories with fewer than this number of candidate articles are skipped.

### Requirement 7: Grouping Trigger API

**User Story:** As a system operator, I want to trigger the RAG-based grouping process via API, so that I can run it on demand after classification completes.

#### Acceptance Criteria

1. THE Article_API SHALL expose the existing `POST /api/groups/generate` endpoint that triggers RAG-based similarity grouping for a specified date.
2. WHEN the generate endpoint is called without a date parameter, THE Grouping_Service SHALL default to grouping articles from today.
3. WHEN the generate endpoint is called with a `date` query parameter (format: YYYY-MM-DD), THE Grouping_Service SHALL group articles from that specific date.
4. THE Grouping_Service SHALL process grouping synchronously and return the result containing the number of groups created, groups updated, and articles grouped.
5. IF no candidate articles are found for the specified date, THEN THE Article_API SHALL return a response indicating zero groups created.
6. THE `POST /api/groups/generate` endpoint SHALL only perform similarity matching and group membership changes — it SHALL NOT generate group detail text (that is handled by the separate regenerate endpoint).

### Requirement 8: Preserve Existing Endpoints and Display

**User Story:** As a reader, I want the feed, group list, and group detail views to continue working unchanged, so that the grouping mechanism change is transparent to the frontend.

#### Acceptance Criteria

1. THE Article_API SHALL continue to expose the `GET /api/feed` endpoint with the same response format and filtering capabilities.
2. THE Article_API SHALL continue to expose the `GET /api/groups` endpoint with the same response format and filtering capabilities.
3. THE Article_API SHALL continue to expose the `GET /api/groups/{id}` endpoint with the same response format including member articles.
4. THE Reader_App SHALL continue to display Article_Groups using the existing GroupCard component without modification.
5. THE Reader_App SHALL continue to display the Group_Detail_Screen with the combined article and member list without modification.
6. THE feed endpoint SHALL continue to exclude grouped articles from appearing as standalone items.

### Requirement 9: Remove LLM Clustering Dependency

**User Story:** As a system operator, I want the LLM clustering calls removed from the grouping flow, so that grouping costs are reduced and latency is improved.

#### Acceptance Criteria

1. THE Grouping_Service SHALL NOT call any LLM for the clustering/similarity decision — similarity is determined solely by vector cosine distance in the Full_Article_Collection.
2. THE Grouping_Service SHALL retain LLM calls only for group detail generation (title, summary, detail).
3. THE Grouping_Service SHALL NOT use the existing `GroupingPipeline.cluster()` method or the clustering LLM prompt.
4. THE Grouping_Service SHALL NOT use the existing `GroupingPipeline.validate_cluster()` method.

### Requirement 10: README Update

**User Story:** As a developer, I want the project README to reflect the new grouping approach, so that documentation stays accurate.

#### Acceptance Criteria

1. WHEN the implementation is complete, THE project README SHALL describe the RAG-based similarity grouping approach instead of the LLM-based clustering approach.
2. THE README SHALL document the new configuration variables (`GROUPING_SIMILARITY_THRESHOLD`, `QDRANT_URL`, `QDRANT_FULL_ARTICLE_COLLECTION`, `EMBEDDING_MODEL`, `EMBEDDING_API_URL`).
3. THE README SHALL explain the grouping flow: embed article → query for similar → threshold check → group or standalone.
