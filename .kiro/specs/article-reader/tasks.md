# Implementation Plan: Article Reader

## Overview

Build a SvelteKit SPA (adapter-static) that displays classified articles from the article-classifier API. Implementation starts with backend changes (CORS + detail endpoint), then scaffolds the SvelteKit project, builds core library code, UI components, page screens, deployment infrastructure, and tests.

## Tasks

- [x] 1. Backend changes to article-classifier API
  - [x] 1.1 Add CORS middleware to article-classifier
    - Add `CORSMiddleware` to `article-classifier/src/main.py`
    - Allow origins: `https://sinalo-reader.fly.dev`, `http://localhost:3000`
    - Allow methods: `GET`
    - Allow headers: `*`
    - _Requirements: 7.7_

  - [x] 1.2 Add `ArticleDetailResponse` schema
    - Create `ArticleDetailResponse` class in `article-classifier/src/schemas.py` extending `ClassifiedArticleResponse`
    - Add `extracted_text: str | None` field
    - _Requirements: 6a.2, 6a.4_

  - [x] 1.3 Implement `GET /api/articles/{id}` endpoint
    - Add route to `article-classifier/src/routes.py`
    - Query `ClassificationResult` joined with `Article` by article ID
    - Use `selectinload` for article, article_tags, tag, and parent relationships
    - Return `ArticleDetailResponse` with all fields including `extracted_text`
    - Return HTTP 404 if article ID doesn't exist or has no classification result
    - _Requirements: 6a.1, 6a.2, 6a.3, 6a.4_

  - [x]* 1.4 Write tests for `GET /api/articles/{id}` endpoint
    - Add tests to `article-classifier/tests/test_routes.py`
    - Test: returns correct data for valid article ID with classification
    - Test: returns 404 for non-existent article ID
    - Test: returns 404 for article without classification result
    - Test: response includes `extracted_text` field
    - _Requirements: 6a.1, 6a.2, 6a.3, 6a.4_

- [x] 2. Checkpoint - Verify backend changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. SvelteKit project scaffolding
  - [x] 3.1 Initialize SvelteKit project with TypeScript and adapter-static
    - Create `article-reader/` directory
    - Initialize SvelteKit project with TypeScript
    - Install dependencies: `@sveltejs/adapter-static`, `tailwindcss`, `marked` (markdown rendering), `vitest`, `fast-check`, `@testing-library/svelte`
    - Configure `svelte.config.js` with `adapter-static` and `fallback: 'index.html'` for SPA mode
    - Configure `vite.config.ts` with Vitest
    - _Requirements: 7.2, 8.1_

  - [x] 3.2 Configure Tailwind CSS
    - Install and configure Tailwind CSS with PostCSS
    - Create `app.css` with Tailwind directives
    - Import in root `+layout.svelte`
    - _Requirements: 8.1, 8.3_

  - [x] 3.3 Set up environment variables
    - Create `.env` with `PUBLIC_ARTICLE_API_URL=http://localhost:8002`
    - Create `.env.example` documenting the variable
    - Create `.gitignore` excluding `.env`, `node_modules/`, `build/`, `.svelte-kit/`
    - _Requirements: 6.1, 7.2, 7.3_

- [x] 4. Core library code (types, API client, stores, utilities)
  - [x] 4.1 Define TypeScript interfaces and types
    - Create `src/lib/types.ts` with: `Tag`, `ArticleSummary`, `ArticleDetail`, `PaginatedResponse`, `CategoryCount`, `Settings`, `ReadState`
    - _Requirements: 6.2, 6a.4_

  - [x] 4.2 Implement API client
    - Create `src/lib/api.ts`
    - Import `PUBLIC_ARTICLE_API_URL` from `$env/static/public`
    - Implement `getArticles(params: ArticleQueryParams): Promise<PaginatedResponse>`
    - Implement `getArticleDetail(id: number): Promise<ArticleDetail>`
    - Implement `getAllArticles(params)` that handles pagination (fetches all pages)
    - Include proper error handling for network errors and HTTP error responses
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 4.3 Implement settings store
    - Create `src/lib/stores/settings.ts`
    - Writable store backed by localStorage key `article-reader:settings`
    - Default values: `{ minScore: 6, daysBack: 7 }`
    - Validate minScore is 0-10, daysBack > 0
    - Load from localStorage on initialization, persist on change
    - _Requirements: 5.2, 5.3, 5.4, 5.7_

  - [x] 4.4 Implement read state store
    - Create `src/lib/stores/readState.ts`
    - Writable store backed by localStorage key `article-reader:read-articles`
    - Store as array of article IDs (`number[]`)
    - Provide `markAsRead(id: number)` and `isRead(id: number)` helpers
    - Articles not in store are treated as unread
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 4.5 Implement utility functions
    - Create `src/lib/utils.ts`
    - `extractCategories(articles: ArticleSummary[]): CategoryCount[]` — groups articles by category, counts per category
    - `buildDateFrom(daysBack: number): string` — computes ISO date string for date_from parameter
    - `extractSubcategories(articles: ArticleSummary[], category: string): string[]` — gets unique subcategories for a category
    - _Requirements: 1.2, 1.3, 2.5_

- [x] 5. Shared UI components
  - [x] 5.1 Create `LoadingSpinner` component
    - Create `src/lib/components/LoadingSpinner.svelte`
    - Centered loading animation using Tailwind
    - _Requirements: 1.6, 2.10_

  - [x] 5.2 Create `ErrorMessage` component
    - Create `src/lib/components/ErrorMessage.svelte`
    - Props: `message: string`, optional `onRetry` callback
    - Display user-friendly error with "Try Again" button
    - _Requirements: 1.5, 2.9, 6.6_

  - [x] 5.3 Create `CategoryCard` component
    - Create `src/lib/components/CategoryCard.svelte`
    - Props: `category: string`, `count: number`
    - Displays category name and article count
    - Clickable, navigates to category page
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 5.4 Create `ArticleCard` component
    - Create `src/lib/components/ArticleCard.svelte`
    - Props: `article: ArticleSummary`, `isRead: boolean`
    - Display summary text as primary content
    - Display publication date and importance score (0-10)
    - Visual read/unread indicator (bold text or colored marker for unread)
    - Clickable, navigates to article detail
    - _Requirements: 2.2, 2.3, 2.4, 8.4, 8.5_

  - [x] 5.5 Create `SubcategoryFilter` component
    - Create `src/lib/components/SubcategoryFilter.svelte`
    - Props: `subcategories: string[]`, `selected: string | null`
    - Chip-based filter UI
    - Dispatches selection event on click
    - _Requirements: 2.5, 2.6_

  - [x] 5.6 Create `MarkdownRenderer` component
    - Create `src/lib/components/MarkdownRenderer.svelte`
    - Props: `content: string`
    - Renders markdown to HTML using `marked` library
    - Supports bold, italic, bullet points
    - _Requirements: 8.2_

- [ ] 6. Page screens and navigation
  - [ ] 6.1 Implement root layout
    - Create `src/routes/+layout.svelte`
    - Import global Tailwind styles
    - Minimal layout wrapper with responsive container
    - _Requirements: 8.1, 8.3_

  - [ ] 6.2 Implement Category Selection Screen
    - Create `src/routes/+page.svelte` and `src/routes/+page.ts`
    - Load function: fetch all articles using current settings (min_score, date_from), extract categories with counts
    - Display categories as `CategoryCard` grid
    - Show `LoadingSpinner` while fetching
    - Show `ErrorMessage` on API error
    - Navigate to `/category/[slug]` on category click
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ] 6.3 Implement Article List Screen
    - Create `src/routes/category/[slug]/+page.svelte` and `+page.ts`
    - Load function: fetch articles filtered by category, min_score, date_from, sorted by published_at asc
    - Display articles as `ArticleCard` list with read/unread indicators
    - Include `SubcategoryFilter` at top
    - Re-fetch with subcategory parameter when filter selected
    - Settings icon (top-right) navigating to `/settings`
    - Reload button that re-fetches data
    - Show `LoadingSpinner` while fetching
    - Show `ErrorMessage` on API error
    - Navigate to `/article/[id]` on card tap
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 6.7_

  - [ ] 6.4 Implement Article Detail Screen
    - Create `src/routes/article/[id]/+page.svelte` and `+page.ts`
    - Load function: fetch article detail from `GET /api/articles/{id}`
    - Display summary section using `MarkdownRenderer`
    - Display full `extracted_text` below summary (if available)
    - Display title, author, publication date, importance score as metadata
    - "Read Original" button linking to article URL (opens in new tab)
    - Hide link button if article has no URL
    - If no `extracted_text`, show summary only + prominent original link
    - Mark article as read in readState store on page load
    - Back navigation to article list
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ] 6.5 Implement Settings Page
    - Create `src/routes/settings/+page.svelte`
    - Load current settings from settings store
    - Min importance score slider/input (0-10, default 6)
    - Days back input (default 7)
    - Save button that persists to localStorage via settings store
    - Back navigation to previous screen
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

- [ ] 7. Checkpoint - Verify app functionality
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Deployment setup
  - [ ] 8.1 Create Dockerfile for static SPA
    - Multi-stage build: Node.js build stage → Nginx production stage
    - Build stage: install deps, build SvelteKit static output
    - Production stage: copy built files to Nginx, serve on port 3000
    - Configure Nginx for SPA fallback (all routes → index.html)
    - Create `.dockerignore` excluding `node_modules/`, `.svelte-kit/`, `build/`, `.git/`
    - _Requirements: 7.1, 7.6_

  - [ ] 8.2 Create `fly.toml` configuration
    - App name: `sinalo-reader`
    - Internal port: 3000
    - HTTP service with auto_stop/auto_start
    - `[env]` section with `PUBLIC_ARTICLE_API_URL` pointing to production article-classifier URL
    - _Requirements: 7.1, 7.2_

  - [ ] 8.3 Create `scripts/start-docker.sh`
    - Parse app name from `fly.toml`
    - Build Docker image
    - Stop/remove existing container
    - Run container with `--env-file .env` on port 3000
    - _Requirements: 7.4_

  - [ ] 8.4 Create `scripts/fly-setup.sh`
    - Parse app name from `fly.toml`
    - Create Fly.io app if not exists
    - Set secrets from `.env` (skip keys in `fly.toml [env]`)
    - _Requirements: 7.5_

  - [ ] 8.5 Update root `deploy.sh` script
    - Add `deploy_reader()` function to deploy article-reader to Fly.io
    - Add `setup_reader()` function to run `article-reader/scripts/fly-setup.sh`
    - Add `reader` case to the case statement for deploying only article-reader
    - Add reader to the `setup` case
    - Add reader to the `all` case
    - Update usage/help text to include the `reader` option
    - _Requirements: 7.1_

- [ ] 9. Property-based tests
  - [ ]* 9.1 Write property test for category extraction
    - **Property 1: Category extraction produces correct counts**
    - Generate arbitrary lists of `ArticleSummary` with random tags
    - Assert: category counts sum to total articles, each count matches articles with that category
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 9.2 Write property tests for read state management
    - **Property 3: Read/unread indicator correctness**
    - **Property 4: Viewing article marks as read (round-trip)**
    - **Property 5: Default unread for unknown articles**
    - Generate arbitrary article IDs and read state sets
    - Assert: isRead returns true iff ID in set; markAsRead adds ID; unknown IDs are unread
    - **Validates: Requirements 2.4, 3.6, 4.1, 4.2, 4.3, 4.5**

  - [ ]* 9.3 Write property tests for settings persistence
    - **Property 6: Settings persistence round-trip**
    - **Property 10: Score validation bounds**
    - Generate arbitrary settings (minScore 0-10, daysBack > 0)
    - Assert: save then load produces identical object; values outside 0-10 are rejected
    - **Validates: Requirements 5.2, 5.4, 5.7**

  - [ ]* 9.4 Write property test for API query parameter construction
    - **Property 7: API query parameter construction**
    - Generate arbitrary combinations of category, subcategory, minScore, daysBack
    - Assert: constructed URL includes all non-null params, sort_by=published_at, sort_order=asc
    - **Validates: Requirements 2.1, 5.5, 6.2, 6.4**

  - [ ]* 9.5 Write property test for pagination calculation
    - **Property 8: Pagination calculation**
    - Generate arbitrary total counts and page sizes
    - Assert: pages needed equals `Math.ceil(total / size)`, all items collected without gaps
    - **Validates: Requirements 6.3**

  - [ ]* 9.6 Write property test for markdown rendering
    - **Property 11: Markdown rendering produces valid HTML**
    - Generate markdown strings with bold, italic, bullet syntax
    - Assert: output HTML contains corresponding `<strong>`, `<em>`, `<li>` elements
    - **Validates: Requirements 8.2**

- [ ] 10. Integration tests
  - [ ]* 10.1 Write integration tests for navigation flow
    - Test: Category Selection → Article List → Article Detail navigation
    - Test: Settings page navigation and back
    - Use mocked API responses
    - _Requirements: 1.4, 2.8, 3.8, 5.1, 5.6, 8.7_

  - [ ]* 10.2 Write integration tests for error handling
    - Test: API unreachable shows error message with retry
    - Test: Article detail 404 shows "not found" with back navigation
    - Test: Reload button re-fetches without triggering classification
    - _Requirements: 1.5, 2.9, 6.6, 6.7_

- [ ] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The design uses TypeScript throughout — all implementation uses TypeScript
- Backend changes (task 1) must be deployed before the frontend can work end-to-end
- The SvelteKit app uses `adapter-static` with SPA fallback — no server-side code
