# Implementation Plan: Article Reader Enhancements

## Overview

This plan implements five client-side enhancements to the existing Article Reader SvelteKit SPA: group read state tracking, "All in one" aggregated category view with date filtering, automatic hiding of read items on re-entry, saved/bookmarked items, and publication time display. Each task builds incrementally on the previous, with stores and utilities implemented first, then UI components, then wiring and integration.

## Tasks

- [x] 1. Add utility functions and types
  - [x] 1.1 Add `SavedItems` interface to `src/lib/types.ts`
    - Add `export interface SavedItems { articles: number[]; groups: number[] }`
    - _Requirements: 4.4, 4.10_
  - [x] 1.2 Add date and sorting utility functions to `src/lib/utils.ts`
    - Add `formatDateTime(dateStr: string | null): string` using `Intl.DateTimeFormat` with user locale for date + time (hours:minutes)
    - Add `formatDateOnly(dateStr: string): string` returning YYYY-MM-DD
    - Add `extractUniqueDates(items: FeedItem[]): string[]` returning unique dates sorted newest-first from `published_at` or `grouped_date`
    - Add `getTodayDateString(): string` returning today as YYYY-MM-DD
    - Add `sortByDateThenImportance(items: FeedItem[]): FeedItem[]` sorting by date descending then importance descending
    - Add `filterReadItems(items: FeedItem[], readArticleIds: number[], readGroupIds: number[], sessionReadSet: Set<string>): FeedItem[]` that excludes read items but preserves session-read items
    - _Requirements: 1.4, 2.2, 2.4, 3.1, 3.2, 3.3, 3.4, 5.1, 5.4_
  - [ ]* 1.3 Write property tests for sorting utility (Property 1)
    - **Property 1: Sort order invariant (date descending, then importance descending)**
    - **Validates: Requirements 1.4**
  - [ ]* 1.4 Write property tests for date extraction (Property 2)
    - **Property 2: Date extraction produces exactly the unique dates present in items**
    - **Validates: Requirements 2.2**
  - [ ]* 1.5 Write property tests for date filtering (Property 3)
    - **Property 3: Date filtering retains only items matching the selected date**
    - **Validates: Requirements 2.4**
  - [ ]* 1.6 Write property tests for read filtering (Properties 4, 5, 6)
    - **Property 4: Read filtering excludes all read items when session set is empty**
    - **Property 5: Session read items are preserved in filtered output**
    - **Property 6: Unread count equals total items minus read items**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6**
  - [ ]* 1.7 Write property test for formatDateTime (Property 11)
    - **Property 11: DateTime formatting includes both date and time components**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5**

- [x] 2. Implement new stores
  - [x] 2.1 Create `src/lib/stores/groupReadState.ts`
    - Create a store backed by localStorage key `article-reader:read-groups`
    - Store value: `number[]` (group IDs)
    - Expose `markGroupAsRead(groupId: number, memberArticleIds: number[])` that adds the group ID to group read state AND marks all member article IDs as read in the existing `readState` store
    - Expose `isGroupRead(id: number): boolean`
    - Follow the same defensive loading pattern as existing `readState.ts` (validate shape, reset on corruption)
    - _Requirements: 3a.1, 3a.3, 3a.4, 3a.5_
  - [x] 2.2 Create `src/lib/stores/savedItems.ts`
    - Create a store backed by localStorage key `article-reader:saved-items`
    - Store value: `{ articles: number[], groups: number[] }`
    - Expose `toggleArticle(id: number)` — adds if not present, removes if present
    - Expose `toggleGroup(id: number)` — adds if not present, removes if present
    - Expose `removeArticle(id: number)` and `removeGroup(id: number)` for explicit removal
    - Expose `isArticleSaved(id: number): boolean` and `isGroupSaved(id: number): boolean`
    - Follow defensive loading pattern (validate shape, reset on corruption)
    - _Requirements: 4.4, 4.5, 4.8, 4.10_
  - [x] 2.3 Create `src/lib/stores/sessionReadSet.ts`
    - Create an in-memory-only writable store (NOT persisted to localStorage)
    - Store value: `Set<string>` where strings are `'article:{id}'` or `'group:{id}'`
    - Expose `add(type: 'article' | 'group', id: number)` and `clear()`
    - Expose `has(type: 'article' | 'group', id: number): boolean`
    - _Requirements: 3.4, 3.5_
  - [ ]* 2.4 Write property tests for group read state (Properties 7, 8)
    - **Property 7: Group read state round-trip**
    - **Property 8: Marking a group as read cascades to all member articles**
    - **Validates: Requirements 3a.1, 3a.3, 3a.4, 3a.5**
  - [ ]* 2.5 Write property tests for saved items store (Properties 9, 10)
    - **Property 9: Saved items toggle is its own inverse**
    - **Property 10: Saved items persistence round-trip**
    - **Validates: Requirements 4.4, 4.5, 4.10**

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement "All in one" category and date filter
  - [ ] 4.1 Modify `src/routes/+page.svelte` to add "All in one" card
    - Add a special "All in one" card at the top of the category list, outside the drag-and-drop reorderable area
    - Display total count of all articles/groups across all categories
    - Give it a visually distinct appearance (e.g., gradient or different color scheme)
    - On click, navigate to `/category/__all__`
    - _Requirements: 1.1, 1.2, 1.5, 1.6_
  - [ ] 4.2 Modify `src/routes/category/[slug]/+page.ts` to handle `__all__` slug
    - When slug is `__all__`, call `getFeed()` without a `category` parameter to fetch all items across all categories
    - Keep existing behavior for regular category slugs
    - _Requirements: 1.3_
  - [ ] 4.3 Create `src/lib/components/DateFilter.svelte`
    - Accept props: `dates: string[]`, `selected: string | null`, `onSelect: (date: string | null) => void`
    - Render a horizontal scrollable row of date chips
    - Display dates in human-readable format (e.g., "Mon, Jan 6")
    - Highlight the selected date chip
    - _Requirements: 2.1, 2.6_
  - [ ] 4.4 Modify `src/routes/category/[slug]/+page.svelte` for date filter and sorting
    - When slug is `__all__`, show `DateFilter` instead of `SubcategoryFilter`
    - Extract unique dates from items using `extractUniqueDates`
    - Default selected date to today (`getTodayDateString()`)
    - Filter items by selected date (client-side)
    - Sort items using `sortByDateThenImportance`
    - Show empty state message when no articles exist for the selected date
    - _Requirements: 1.4, 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 5. Implement read filtering and group read state in UI
  - [ ] 5.1 Modify `src/routes/category/[slug]/+page.svelte` for read filtering
    - Import `groupReadState`, `readState`, and `sessionReadSet` stores
    - Apply `filterReadItems` to the items list before rendering (filter out read articles and groups, but keep session-read items visible)
    - When user reads an article/group and returns, add the item to `sessionReadSet` so it stays visible with a read indicator
    - Clear `sessionReadSet` on navigation away (use `beforeNavigate` or `onDestroy`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - [ ] 5.2 Modify `src/routes/+page.svelte` and `CategoryCard` to show read/unread/total counts
    - Compute per-category: total items, read items, unread items
    - Update `CategoryCard` to accept and display all three counts (e.g., "3 read / 7 unread / 10 total")
    - The "All in one" card should also display read/unread/total counts
    - _Requirements: 3.6_
  - [ ] 5.3 Modify `src/routes/group/[id]/+page.svelte` to mark group as read
    - On mount, call `groupReadState.markGroupAsRead(group.id, memberArticleIds)` which marks the group AND all member articles as read
    - _Requirements: 3a.3, 3a.4_
  - [ ] 5.4 Modify `GroupCard.svelte` for read/unread indicator and mark-as-read button
    - Accept new props: `isRead: boolean`, `onMarkRead?: (id: number) => void`
    - Show unread indicator (blue dot) consistent with `ArticleCard`
    - Add a "Mark as read" button that calls `onMarkRead` without navigating
    - _Requirements: 3a.2, 3a.6_
  - [ ] 5.5 Wire GroupCard read state in `category/[slug]/+page.svelte`
    - Pass `isRead` prop to `GroupCard` based on `groupReadState`
    - Pass `onMarkRead` handler that calls `groupReadState.markGroupAsRead` with the group's member article IDs (fetch group detail or use available data)
    - _Requirements: 3a.2, 3a.6_

- [ ] 6. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement saved/bookmarked items feature
  - [ ] 7.1 Create `src/lib/components/SaveButton.svelte`
    - Accept props: `isSaved: boolean`, `onToggle: () => void`
    - Render a bookmark icon (filled when saved, outline when unsaved)
    - Visually indicate saved/unsaved state
    - _Requirements: 4.9_
  - [ ] 7.2 Add save button to `src/routes/article/[id]/+page.svelte`
    - Import `savedItems` store and `SaveButton` component
    - Place save button next to the "Read Original" button
    - Toggle saved state on click using `savedItems.toggleArticle(id)`
    - _Requirements: 4.2, 4.4, 4.5, 4.9_
  - [ ] 7.3 Add save button to `src/routes/group/[id]/+page.svelte`
    - Import `savedItems` store and `SaveButton` component
    - Place save button in the group detail header area
    - Toggle saved state on click using `savedItems.toggleGroup(id)`
    - _Requirements: 4.3, 4.4, 4.5, 4.9_
  - [ ] 7.4 Create saved items page at `src/routes/saved/+page.ts`
    - Load saved item IDs from the `savedItems` store
    - Fetch article details for each saved article ID using `getArticleDetail`
    - Fetch group details for each saved group ID using `getGroupDetail`
    - Handle 404 responses gracefully (mark items as unavailable)
    - Display items in reverse insertion order (most recently saved first)
    - _Requirements: 4.7, 4.8, 4.12_
  - [ ] 7.5 Create saved items page at `src/routes/saved/+page.svelte`
    - Display all saved articles and groups regardless of read state
    - Show articles using `ArticleCard` and groups using `GroupCard`
    - Provide a remove button on each item to unsave it
    - Show unavailable items with a "remove from saved" option
    - Show empty state when no items are saved
    - _Requirements: 4.1, 4.6, 4.9, 4.12_
  - [ ] 7.6 Add navigation link to saved page in `src/routes/+layout.svelte` or `+page.svelte`
    - Add a link/button to access the saved items page from the category selection screen
    - _Requirements: 4.1_

- [ ] 8. Implement publication time display
  - [ ] 8.1 Update `ArticleCard.svelte` to show publication time
    - Replace the existing `formatDate` call with `formatDateTime` from utils
    - Display both date and time (e.g., "Jan 6, 2025 14:30")
    - If `published_at` is null, display nothing
    - _Requirements: 5.1, 5.4, 5.5_
  - [ ] 8.2 Update `GroupCard.svelte` to show publication time
    - Replace the existing `formatDate` call with `formatDateTime` from utils
    - Display both date and time for `grouped_date`
    - _Requirements: 5.3, 5.4_
  - [ ] 8.3 Update `article/[id]/+page.svelte` to show publication time
    - Replace the existing `formatDate` call with `formatDateTime` from utils
    - Display both date and time in the article detail header
    - _Requirements: 5.2, 5.4, 5.5_

- [ ] 9. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- All enhancements are client-side only — no backend changes needed
- The existing `getFeed()` API already supports all needed query parameters
- fast-check is already installed for property-based testing
