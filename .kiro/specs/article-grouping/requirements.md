# Requirements Document

## Introduction

The Article Grouping system is a post-classification feature that identifies and clusters similar articles covering the same topic from different sources within a single day and category. It reduces information duplication by generating consolidated AI summaries for article groups, while preserving access to all original sources. Groups appear alongside regular articles in the reader application, providing a streamlined reading experience where clicking a group reveals a longer combined article with links to all original sources.

## Glossary

- **Grouping_Service**: The component within the article-classifier service responsible for comparing classified article summaries and clustering similar articles into groups.
- **Article_Group**: A collection of two or more classified articles that cover the same topic or event from different sources, published on the same day within the same category.
- **Group_Summary**: A short one-paragraph AI-generated text in Czech that describes the group topic, used for display on group cards in the article list.
- **Group_Detail**: A longer AI-generated article in Czech (2-5 paragraphs) that combines and synthesizes information from all member articles' full texts, formatted in Markdown, displayed on the Group Detail Screen.
- **Standalone_Article**: A classified article that does not belong to any group because no sufficiently similar articles were found.
- **Similarity_Assessment**: The LLM-based evaluation that determines whether two or more articles cover the same topic or event.
- **Grouping_Pipeline**: The LangGraph-based AI pipeline that performs similarity assessment and generates consolidated group summaries.
- **Group_Member**: An individual article that belongs to an Article_Group, with a reference to the original article record.
- **Reader_App**: The SvelteKit web application that displays articles and article groups to the user.
- **Article_API**: The article-classifier service's REST API that provides classified article data and group data.

## Requirements

### Requirement 1: Identify Candidate Articles for Grouping

**User Story:** As a system operator, I want the grouping service to identify classified articles eligible for grouping, so that only fully processed articles from the same day and category are compared.

#### Acceptance Criteria

1. WHEN the grouping process is triggered, THE Grouping_Service SHALL select classified articles from the specified date (default: today) based on `published_at`, that have not yet been assigned to any Article_Group.
2. THE Grouping_Service SHALL group candidate articles by their first assigned tag category (the first tag returned by the classifier) before performing similarity assessment, to reduce the number of articles compared in a single LLM call.
3. THE Grouping_Service SHALL only compare articles within the same category — articles from different categories SHALL NOT be grouped together.
4. THE Grouping_Service SHALL only consider articles that have a classification result with a summary available.
5. IF fewer than GROUPING_MIN_ARTICLES (default: 2) candidate articles exist in a category for the specified date, THEN THE Grouping_Service SHALL skip similarity assessment for that category.
6. WHEN grouping is triggered for a date where groups already exist, THE Grouping_Service SHALL include existing groups (with their title and summary) alongside ungrouped articles in the clustering input, so the LLM can decide whether new articles should be added to an existing group or form a new one.
7. IF the LLM assigns a new article to an existing group, THEN THE Grouping_Service SHALL add the article to that group's membership and regenerate the group's summary and detail.
8. IF no new articles were added to an existing group during a re-run, THEN THE Grouping_Service SHALL NOT regenerate that group's summary and detail.

### Requirement 2: Assess Article Similarity

**User Story:** As a reader, I want similar articles about the same specific topic to be identified automatically, so that I see consolidated information instead of duplicates.

#### Acceptance Criteria

1. WHEN candidate articles are available for a category, THE Grouping_Pipeline SHALL send article summaries and titles to the LLM to assess which articles cover the same specific topic, event, or story.
2. THE Grouping_Pipeline SHALL instruct the LLM to group articles only when they discuss the same concrete thing (e.g., the same incident, announcement, decision, or event) — NOT based on abstract thematic similarity or shared category.
3. THE Grouping_Pipeline SHALL instruct the LLM to return clusters of article IDs that cover the same topic, along with a brief justification for each cluster.
4. THE Grouping_Pipeline SHALL allow articles to remain ungrouped (standalone) when no sufficiently similar articles exist.
5. THE Grouping_Pipeline SHALL use a single LLM call per category to assess all candidate articles simultaneously, rather than pairwise comparisons.
6. THE Grouping_Pipeline SHALL include article titles, summaries, and publication sources in the similarity assessment prompt to enable accurate topic matching.
7. WHEN existing groups are present for the date, THE Grouping_Pipeline SHALL include group titles and summaries in the clustering prompt so the LLM can assign new articles to existing groups.
8. IF the LLM returns a group containing only one article, THEN THE Grouping_Service SHALL discard that group and treat the article as standalone.
9. THE Grouping_Pipeline SHALL not place the same article in multiple groups — each article SHALL belong to at most one group.

### Requirement 3: Generate Group Content

**User Story:** As a reader, I want each article group to have both a short summary for browsing and a full combined article for reading, so that I can quickly scan topics in the list and read the complete consolidated information when interested.

#### Acceptance Criteria

1. WHEN an Article_Group is formed, THE Grouping_Pipeline SHALL generate two text outputs for each group: a short Group_Summary and a long Group_Detail.
2. THE Grouping_Pipeline SHALL generate the Group_Summary as a concise one-paragraph text in Czech, suitable for display on a group card in the article list.
3. THE Grouping_Pipeline SHALL generate the Group_Detail as a longer article (approximately 2-5 paragraphs) in Czech Markdown, combining key facts, perspectives, and conclusions from all source articles.
4. THE Grouping_Pipeline SHALL use the full `extracted_text` of each member article as input for generating the Group_Detail — not just the article summaries.
5. THE Grouping_Pipeline SHALL generate both outputs in Czech language regardless of the original article languages.
6. THE Grouping_Pipeline SHALL include information about differing perspectives or angles in the Group_Detail when member articles present the topic differently.
7. THE Grouping_Pipeline SHALL generate a concise group title in Czech that describes the shared topic.
8. IF a member article contains unique facts not present in other members, THEN THE Grouping_Pipeline SHALL include those facts in the Group_Detail.
9. THE Grouping_Pipeline SHALL not fabricate information — both Group_Summary and Group_Detail SHALL only contain information present in the member articles.

### Requirement 4: Persist Article Groups

**User Story:** As a developer, I want article groups stored in the database with proper relationships, so that groups can be queried and displayed efficiently.

#### Acceptance Criteria

1. THE Grouping_Service SHALL store each Article_Group in an `article_groups` table with: id, title, summary, detail, category, grouped_date, created_at.
2. THE Grouping_Service SHALL store group membership in an `article_group_members` table with: id, group_id (FK to article_groups), article_id (FK to articles), created_at.
3. THE Grouping_Service SHALL enforce a unique constraint on article_id in the `article_group_members` table to prevent an article from belonging to multiple groups.
4. THE Grouping_Service SHALL store the category as a string reference to the primary tag category used during grouping.
5. THE Grouping_Service SHALL store the grouped_date as the date for which the grouping was performed.
6. THE Grouping_Service SHALL store the LLM model used and token count for each grouping operation in the `article_groups` table metadata.
7. IF a grouping operation fails after partial persistence, THEN THE Grouping_Service SHALL roll back the transaction to maintain data consistency.

### Requirement 5: Grouping Trigger API

**User Story:** As a system operator, I want to trigger the grouping process via API, so that I can run it on demand after classification completes.

#### Acceptance Criteria

1. THE Article_API SHALL expose a `POST /api/groups/generate` endpoint that triggers grouping for a specified date.
2. WHEN the generate endpoint is called without a date parameter, THE Grouping_Service SHALL default to grouping articles from today.
3. WHEN the generate endpoint is called with a `date` query parameter (format: YYYY-MM-DD), THE Grouping_Service SHALL group articles from that specific date.
4. THE Grouping_Service SHALL process grouping synchronously and return the result containing the number of groups created and articles grouped.
5. IF grouping has already been performed for the specified date, THEN THE Grouping_Service SHALL include existing groups in the clustering input and process only ungrouped articles as new candidates — the LLM may assign new articles to existing groups or create new groups.
6. IF no candidate articles are found for the specified date, THEN THE Article_API SHALL return a response indicating zero groups created.

### Requirement 6: Group Retrieval API

**User Story:** As a frontend developer, I want API endpoints to retrieve article groups, so that the reader app can display groups alongside regular articles.

#### Acceptance Criteria

1. THE Article_API SHALL expose a `GET /api/groups` endpoint that returns article groups with filtering support.
2. THE Article_API SHALL support filtering groups by category via query parameter `category`.
3. THE Article_API SHALL support filtering groups by date via query parameter `date` (format: YYYY-MM-DD).
4. THE Article_API SHALL support filtering groups by date range via query parameters `date_from` and `date_to`.
5. THE Article_API SHALL return for each group: id, title, summary, category, grouped_date, member_count, created_at.
6. THE Article_API SHALL expose a `GET /api/groups/{id}` endpoint that returns a single group with full details including all member articles.
7. WHEN the group detail endpoint is called, THE Article_API SHALL return the group title, summary, detail (full combined article), and a list of all member articles with their: id, title, url, author, published_at, summary, importance_score.
8. IF the group ID does not exist, THEN THE Article_API SHALL return HTTP 404.
9. THE Article_API SHALL support pagination on the groups list endpoint with `page` and `size` query parameters (default page=1, size=20).

### Requirement 7: Mixed Feed API

**User Story:** As a frontend developer, I want a unified feed that interleaves groups and standalone articles, so that the reader app can display them together in chronological order.

#### Acceptance Criteria

1. THE Article_API SHALL expose a `GET /api/feed` endpoint that returns a mixed list of article groups and standalone articles for a given category and date range.
2. THE feed endpoint SHALL support filtering by category via query parameter `category`.
3. THE feed endpoint SHALL support filtering by date range via query parameters `date_from` and `date_to`.
4. THE feed endpoint SHALL support filtering by minimum importance score via query parameter `min_score`.
5. THE feed endpoint SHALL support filtering by subcategory via query parameter `subcategory` — for groups, this matches if at least one member article has the specified subcategory tag.
6. WHEN returning groups, THE feed endpoint SHALL include: type="group", id, title, summary (short one-paragraph text), category, grouped_date, member_count.
7. WHEN returning standalone articles, THE feed endpoint SHALL include: type="article", and all standard classified article fields.
8. THE feed endpoint SHALL NOT return articles that are members of any Article_Group as standalone items — grouped articles appear only within their group.
9. THE feed endpoint SHALL sort items by date (published_at for articles, grouped_date for groups) in ascending order.
10. THE feed endpoint SHALL support pagination with `page` and `size` query parameters (default page=1, size=20).
11. THE feed endpoint SHALL calculate importance_score for groups as the maximum importance_score among member articles.
12. WHEN filtering by subcategory, THE feed endpoint SHALL include a group if at least one of its member articles has the specified subcategory tag.

### Requirement 8: Reader App Group Display

**User Story:** As a reader, I want article groups to appear in the article list alongside regular articles, so that I can see consolidated topics without switching views.

#### Acceptance Criteria

1. WHEN the Article_List_Screen is displayed, THE Reader_App SHALL fetch data from the feed endpoint instead of the articles endpoint.
2. THE Reader_App SHALL display Article_Groups as a distinct card type with a visual indicator showing it is a group (e.g., stacked card appearance or group icon).
3. THE Reader_App SHALL display the group title, group summary (short text), member count, and grouped_date on the group card.
4. THE Reader_App SHALL display the maximum importance score of the group's member articles on the group card.
5. WHEN the user taps a group card, THE Reader_App SHALL navigate to a Group_Detail_Screen.
6. THE Reader_App SHALL continue to display standalone articles using the existing Article_Card component.

### Requirement 9: Reader App Group Detail Screen

**User Story:** As a reader, I want to see the full combined article for a group and navigate to individual article details, so that I can read the consolidated information and drill down into specific sources when needed.

#### Acceptance Criteria

1. WHEN the Group_Detail_Screen is displayed, THE Reader_App SHALL fetch group details from the `GET /api/groups/{id}` endpoint.
2. THE Reader_App SHALL display the group title and the full Group_Detail (long combined article) rendered as Markdown.
3. THE Reader_App SHALL display a list of all member articles below the summary, showing each article's title, author, source domain, and publication date.
4. WHEN the user taps a member article in the list, THE Reader_App SHALL navigate to the existing Article_Detail_Screen for that article (internal navigation, not external link).
5. THE Reader_App SHALL NOT link directly to original article URLs from the Group_Detail_Screen — the user reaches original sources only through the Article_Detail_Screen.
6. THE Reader_App SHALL provide navigation back to the Article_List_Screen.
7. WHEN the Group_Detail_Screen is displayed, THE Reader_App SHALL mark all member articles as read in the Read_State.

### Requirement 10: Grouping Pipeline Efficiency

**User Story:** As a system operator, I want the grouping pipeline to be cost-efficient, so that LLM API costs remain manageable.

#### Acceptance Criteria

1. THE Grouping_Pipeline SHALL perform similarity assessment in a single LLM call per category (clustering call).
2. THE Grouping_Pipeline SHALL generate the Group_Detail and Group_Summary for each group in a separate LLM call per group, using the full `extracted_text` of member articles as input.
3. THE Grouping_Pipeline SHALL only call detail generation for newly created groups or existing groups that received new member articles — unchanged groups SHALL NOT trigger a detail generation call.
4. THE Grouping_Pipeline SHALL use structured output (JSON) for the clustering step with the following structure:
   ```json
   {
     "groups": [
       {
         "article_ids": [1, 2, 3],
         "topic": "Brief topic description",
         "justification": "Why these articles are grouped"
       }
     ],
     "existing_group_additions": [
       {
         "group_id": 42,
         "article_ids": [6, 7]
       }
     ],
     "standalone_ids": [4, 5]
   }
   ```
5. THE Grouping_Pipeline SHALL use structured output (JSON) for each group's detail generation call with the following structure:
   ```json
   {
     "title": "Group title in Czech",
     "summary": "Short one-paragraph summary in Czech for list display",
     "detail": "Long combined article in Czech Markdown (2-5 paragraphs)"
   }
   ```
6. IF an LLM API call fails with a rate limit error (HTTP 429), THEN THE Grouping_Pipeline SHALL retry after a configurable delay up to 3 times.
7. IF an LLM API call fails with a non-retryable error, THEN THE Grouping_Pipeline SHALL log the error and skip that group (or category for clustering).
8. THE Grouping_Service SHALL record the LLM model used and total token count for each grouping operation.

### Requirement 11: Grouping Configuration

**User Story:** As a developer, I want grouping configuration externalized via environment variables, so that behavior can be tuned without code changes.

#### Acceptance Criteria

1. THE Grouping_Service SHALL reuse the existing article-classifier configuration (DATABASE_URL, OPENROUTER_API_KEY, LLM_MODEL).
2. THE Grouping_Service SHALL support an optional `GROUPING_LLM_MODEL` environment variable to use a different model for grouping (default: same as LLM_MODEL).
3. THE Grouping_Service SHALL support a `GROUPING_MIN_ARTICLES` environment variable specifying the minimum number of ungrouped articles in a category required to trigger clustering (default: 2).
4. THE Grouping_Service SHALL support a `GROUPING_MAX_ARTICLES_PER_CATEGORY` environment variable limiting how many articles are sent to the LLM in a single clustering call (default: 50).
5. IF the number of candidate articles in a category exceeds GROUPING_MAX_ARTICLES_PER_CATEGORY, THEN THE Grouping_Service SHALL process only the most recent articles up to the limit.

### Requirement 12: CLI Script Extension

**User Story:** As a system operator, I want CLI commands for triggering and inspecting grouping, so that I can manage the grouping process from the command line.

#### Acceptance Criteria

1. THE classifier CLI script SHALL support a `classifier group` command that triggers grouping for today's articles.
2. THE classifier CLI script SHALL support a `classifier group --date=YYYY-MM-DD` option to trigger grouping for a specific date.
3. THE classifier CLI script SHALL support a `classifier groups` command that lists recent article groups.
4. THE classifier CLI script SHALL support a `classifier groups --category=Technology` option to filter groups by category.
5. THE classifier CLI script SHALL support a `classifier group-detail <id>` command that shows full group details including member articles.
