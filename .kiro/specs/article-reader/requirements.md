# Requirements Document

## Introduction

The Article Reader is a SvelteKit web application that provides a clean, reader-friendly interface for browsing and reading classified articles from the article-classifier API. The application focuses on displaying article summaries as a digest, organized by category and subcategory. It supports filtering by importance score and date range, tracks read/unread status locally in the browser, and is designed for potential future wrapping in Capacitor for mobile deployment.

## Glossary

- **Reader_App**: The SvelteKit web application that displays classified articles to the user.
- **Article_API**: The article-classifier service's `GET /api/articles` endpoint that provides classified article data.
- **Category**: A top-level topic tag (e.g., Technology, Politics, Economy) assigned to articles by the classifier.
- **Subcategory**: A second-level topic tag under a category (e.g., AI, Cybersecurity under Technology).
- **Article_Card**: A UI element in the article list displaying the summary text and read/unread indicator for a single article.
- **Read_State**: A per-article boolean stored in browser localStorage indicating whether the user has viewed the article detail.
- **Settings**: User-configurable filter parameters (importance score range, date range) that persist in browser localStorage.
- **Category_Selection_Screen**: The entry point screen showing all categories with their article counts.
- **Article_List_Screen**: The screen showing articles for a selected category, sorted oldest to newest.
- **Article_Detail_Screen**: The screen showing the full article summary with a link to the original article URL.

## Requirements

### Requirement 1: Category Selection Screen

**User Story:** As a reader, I want to see all available categories with article counts, so that I can choose which topic to browse.

#### Acceptance Criteria

1. WHEN the user opens the application, THE Reader_App SHALL display the Category_Selection_Screen as the entry point.
2. THE Reader_App SHALL fetch articles from the Article_API using the current Settings filter values (min_score and date_from) and display each unique category as a selectable card.
3. THE Reader_App SHALL display the number of articles available for each category, calculated based on the current filter settings.
4. WHEN the user selects a category, THE Reader_App SHALL navigate to the Article_List_Screen for that category.
5. IF the Article_API returns an error, THEN THE Reader_App SHALL display an error message indicating the data could not be loaded.
6. WHILE the data is being fetched from the Article_API, THE Reader_App SHALL display a loading indicator.

### Requirement 2: Article List Screen

**User Story:** As a reader, I want to see article summaries for a category sorted oldest to newest, so that I can read a chronological digest of what happened.

#### Acceptance Criteria

1. WHEN the Article_List_Screen is displayed, THE Reader_App SHALL fetch articles from the Article_API filtered by the selected category, current min_score, and date_from settings, sorted by `published_at` in ascending order.
2. THE Reader_App SHALL display each article as an Article_Card with the summary text as the primary content.
3. THE Reader_App SHALL display the publication date and importance score (0–10) on each Article_Card.
4. THE Reader_App SHALL display a visual indicator on each Article_Card showing whether the article has been read or is unread based on the Read_State.
5. THE Reader_App SHALL display a subcategory filter that allows the user to narrow articles to a specific subcategory within the current category.
6. WHEN the user selects a subcategory filter, THE Reader_App SHALL re-fetch articles from the Article_API with the subcategory parameter applied.
7. THE Reader_App SHALL display a settings icon in the top-right corner that navigates to the Settings page.
8. THE Reader_App SHALL display a reload button that re-fetches data from the Article_API without triggering any classification process.
9. WHEN the user taps an Article_Card, THE Reader_App SHALL navigate to the Article_Detail_Screen for that article.
10. IF the Article_API returns an error during fetch or reload, THEN THE Reader_App SHALL display an error message.
11. WHILE data is being fetched, THE Reader_App SHALL display a loading indicator.

### Requirement 3: Article Detail Screen

**User Story:** As a reader, I want to see both the article summary and the full parsed article text, so that I can get complete information without leaving the app.

#### Acceptance Criteria

1. WHEN the Article_Detail_Screen is displayed, THE Reader_App SHALL show the article summary text as the first section.
2. THE Reader_App SHALL display the full parsed article text (`extracted_text`) below the summary section.
3. THE Reader_App SHALL display the article title, author, publication date, and importance score (0–10) when available.
4. THE Reader_App SHALL display a button linking to the original article URL that opens in a new browser tab, intended for verification or when the full text is unavailable.
5. IF the article has no `extracted_text`, THEN THE Reader_App SHALL display only the summary and prominently show the link to the original article.
6. WHEN the Article_Detail_Screen is displayed, THE Reader_App SHALL mark the article as read in the Read_State.
7. IF the article has no URL, THEN THE Reader_App SHALL hide the link button to the original article.
8. THE Reader_App SHALL provide navigation back to the Article_List_Screen.

### Requirement 4: Read/Unread State Management

**User Story:** As a reader, I want to see which articles I have already read, so that I can focus on new content.

#### Acceptance Criteria

1. THE Reader_App SHALL store the Read_State for each article using the article ID as the key in browser localStorage.
2. WHEN the user views an article on the Article_Detail_Screen, THE Reader_App SHALL mark that article's Read_State as read.
3. THE Reader_App SHALL display unread articles with a distinct visual indicator (e.g., bold text or colored marker) on the Article_List_Screen.
4. THE Reader_App SHALL persist Read_State across browser sessions using localStorage.
5. THE Reader_App SHALL treat articles without a stored Read_State as unread.

### Requirement 5: Settings Page

**User Story:** As a reader, I want to configure importance score and date range filters, so that I only see articles that meet my relevance threshold.

#### Acceptance Criteria

1. THE Reader_App SHALL provide a Settings page accessible from the settings icon on the Article_List_Screen.
2. THE Reader_App SHALL allow the user to set a minimum importance score filter with a range of 0 to 10 (default: 6).
3. THE Reader_App SHALL allow the user to set a date range filter specifying how far back to fetch articles (default: last 7 days).
4. THE Reader_App SHALL persist all settings in browser localStorage.
5. WHEN the user changes settings, THE Reader_App SHALL apply the new filter values on the next data fetch.
6. THE Reader_App SHALL provide navigation back to the previous screen after settings are saved.
7. THE Reader_App SHALL load previously saved settings from localStorage when the Settings page is opened.

### Requirement 6: API Integration

**User Story:** As a reader, I want the application to fetch data from the article-classifier API, so that I can view classified articles.

#### Acceptance Criteria

1. THE Reader_App SHALL communicate with the Article_API at a configurable base URL via environment variable.
2. THE Reader_App SHALL use the following query parameters when fetching articles: `min_score`, `date_from`, `category`, `subcategory`, `sort_by`, `sort_order`, `page`, `size`.
3. THE Reader_App SHALL handle pagination by fetching all pages needed to display complete category counts and article lists.
4. THE Reader_App SHALL set `sort_by` to `published_at` and `sort_order` to `asc` for the Article_List_Screen.
5. THE Reader_App SHALL fetch article detail (including `extracted_text`) from a dedicated detail endpoint `GET /api/articles/{id}` on the Article_API.
6. IF the Article_API is unreachable, THEN THE Reader_App SHALL display a user-friendly error message indicating the service is unavailable.
7. THE Reader_App SHALL not trigger any classification process — the reload button only re-fetches existing data.

### Requirement 6a: Article Detail API Endpoint (Backend)

**User Story:** As a frontend developer, I want a detail endpoint on the article-classifier API that returns the full article data including extracted_text, so that the reader app can display the complete article.

#### Acceptance Criteria

1. THE Article_API SHALL expose a `GET /api/articles/{id}` endpoint that returns a single classified article with all fields including `extracted_text`.
2. THE endpoint SHALL return the same fields as the list endpoint plus the `extracted_text` field from the articles table.
3. IF the article ID does not exist or has no classification result, THEN THE endpoint SHALL return HTTP 404.
4. THE endpoint response SHALL include: id, title, url, author, published_at, tags, content_type, importance_score, summary, extracted_text, classified_at.

### Requirement 7: Deployment and Configuration

**User Story:** As a developer, I want the application deployed to Fly.io as a static SPA, so that it is consistent with other services in the workspace.

#### Acceptance Criteria

1. THE Reader_App SHALL be deployable to Fly.io using a Dockerfile that serves static files via Nginx or similar.
2. THE Reader_App SHALL read the Article_API base URL from a public environment variable `PUBLIC_ARTICLE_API_URL` at build time.
3. THE Reader_App SHALL provide a `.env.example` file documenting all required environment variables.
4. THE Reader_App SHALL include a `start-docker.sh` script for local Docker development.
5. THE Reader_App SHALL include a `fly-setup.sh` script for Fly.io app creation and configuration.
6. THE Reader_App SHALL serve on port 3000 by default inside the container.
7. THE article-classifier API SHALL enable CORS for the Reader_App's origin to allow direct browser requests.

### Requirement 8: User Interface Design

**User Story:** As a reader, I want a clean, minimal interface optimized for reading summaries, so that I can quickly digest article content.

**Design Reference:** The visual layout and screen structure SHALL follow the mockup provided in `.design/Screenshot 2026-05-07 075924.png`.

#### Acceptance Criteria

1. THE Reader_App SHALL use a clean, minimal visual design focused on readability of summary text, following the layout shown in the design reference.
2. THE Reader_App SHALL render article summaries with Markdown formatting support (bold, italic, bullet points).
3. THE Reader_App SHALL be responsive and usable on both desktop and mobile screen sizes.
4. THE Reader_App SHALL prioritize summary text as the primary content on Article_Cards rather than article titles.
5. THE Reader_App SHALL display article metadata (title, author, date, importance score) as secondary information below or above the summary.
6. THE Reader_App SHALL support future wrapping in Capacitor for mobile app distribution without requiring architectural changes.
7. THE Reader_App SHALL implement the three-screen navigation flow (Category Selection → Article List → Article Detail) as shown in the design reference.
