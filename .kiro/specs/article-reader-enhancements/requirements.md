# Requirements Document

## Introduction

This document specifies enhancements to the existing Article Reader SvelteKit application. The enhancements introduce an "All in one" aggregated category view with date-based filtering, automatic hiding of previously read articles and groups upon re-entry, read/unread state tracking for article groups, a saved/bookmarked articles and groups feature, and display of publication time alongside dates. These features build on the existing category selection, article list, article detail, read state tracking, and feed/group infrastructure already present in the application.

## Glossary

- **Reader_App**: The existing SvelteKit web application that displays classified articles to the user.
- **All_In_One_Category**: A special virtual category always displayed at the top of the category list that aggregates all articles and groups across all categories, sorted by date and importance.
- **Date_Filter**: A UI filter component in the All_In_One_Category view that allows the user to select a specific date to narrow displayed articles and groups to that day.
- **Read_State**: A per-article and per-group boolean stored in browser localStorage indicating whether the user has viewed the article detail or group detail.
- **Session_Read_Set**: A transient in-memory set of article IDs and group IDs marked as read during the current viewing session, used to keep recently-read items visible until the user navigates away or restarts the app.
- **Saved_Items_Store**: A persistent list of article IDs and group IDs stored in browser localStorage representing items the user has explicitly bookmarked/saved.
- **Saved_Articles_Page**: A dedicated page displaying all saved/bookmarked articles and groups regardless of their read state.
- **Group_Detail_Screen**: The screen showing the group summary, full detail text, and list of member articles.
- **Publication_Time**: The time-of-day portion of the `published_at` timestamp from the article-classifier API.
- **Category_Selection_Screen**: The entry point screen showing all categories with their article counts.
- **Article_List_Screen**: The screen showing articles for a selected category.
- **Article_Detail_Screen**: The screen showing the full article summary with a link to the original article URL.

## Requirements

### Requirement 1: All In One Special Category

**User Story:** As a reader, I want a special "All in one" category always shown at the top of the category list, so that I can see all articles from all categories in a single aggregated view sorted by date and importance.

#### Acceptance Criteria

1. THE Reader_App SHALL display the All_In_One_Category as the first item in the Category_Selection_Screen, positioned above all user-reorderable categories.
2. THE All_In_One_Category SHALL display the total count of all articles and groups across all categories based on the current filter settings.
3. WHEN the user selects the All_In_One_Category, THE Reader_App SHALL navigate to the Article_List_Screen showing all articles and groups from all categories.
4. THE Reader_App SHALL sort items in the All_In_One_Category view by published date descending and then by importance score descending within the same date.
5. THE All_In_One_Category SHALL NOT be affected by the drag-and-drop reordering of other categories on the Category_Selection_Screen.
6. THE All_In_One_Category SHALL have a visually distinct appearance from regular categories to indicate its special aggregation role.

### Requirement 2: Date-Based Filtering in All In One View

**User Story:** As a reader, I want to filter articles by date in the "All in one" view instead of subcategory filters, so that I can focus on articles from a specific day.

#### Acceptance Criteria

1. WHEN the All_In_One_Category view is displayed, THE Reader_App SHALL show a Date_Filter component instead of the subcategory filter.
2. THE Date_Filter SHALL display selectable date options derived from the available articles within the current settings date range.
3. THE Reader_App SHALL default the Date_Filter selection to today's date when the All_In_One_Category view is first opened.
4. WHEN the user selects a date in the Date_Filter, THE Reader_App SHALL display only articles and groups with a published date matching the selected date.
5. IF no articles exist for today's date, THEN THE Reader_App SHALL display an empty state message indicating no articles are available for the selected date.
6. THE Date_Filter SHALL display dates in a human-readable format consistent with the rest of the application.

### Requirement 3: Hide Read Articles on Re-Entry

**User Story:** As a reader, I want previously read articles and groups to be hidden when I reopen the app or navigate to a different category, so that I only see unread content and can focus on new articles.

#### Acceptance Criteria

1. WHEN the user opens the Reader_App after a previous session, THE Reader_App SHALL exclude articles and groups whose IDs are present in the Read_State from the Article_List_Screen.
2. WHEN the user navigates from one category to another category, THE Reader_App SHALL exclude articles and groups whose IDs are present in the Read_State from the newly displayed Article_List_Screen.
3. WHEN the user triggers a reload of articles within the current view, THE Reader_App SHALL exclude articles and groups whose IDs are present in the Read_State from the refreshed Article_List_Screen.
4. WHILE the user remains in the same Article_List_Screen view after reading an article or group, THE Reader_App SHALL continue to display that item with a read indicator in the Session_Read_Set.
5. WHEN the user navigates away from the Article_List_Screen and returns, THE Reader_App SHALL clear the Session_Read_Set and hide all previously read articles and groups.
6. THE Reader_App SHALL display on each category card in the Category_Selection_Screen the total item count, the read count, and the unread count, so the user can see how many items are read, unread, and the total (e.g., "3 read / 7 unread / 10 total").

### Requirement 3a: Group Read State Management

**User Story:** As a reader, I want groups to have the same read/unread tracking as individual articles, so that I can see which groups I have already reviewed.

#### Acceptance Criteria

1. THE Reader_App SHALL store the Read_State for each group using the group ID in a separate browser localStorage key dedicated to group read state.
2. THE Reader_App SHALL display unread groups with a distinct visual indicator (consistent with unread articles) on the Article_List_Screen.
3. WHEN the user opens the Group_Detail_Screen, THE Reader_App SHALL mark the group as read in the Read_State.
4. WHEN a group is marked as read, THE Reader_App SHALL also mark all member articles of that group as read in the Read_State.
5. THE Reader_App SHALL treat groups without a stored Read_State as unread.
6. THE Reader_App SHALL display a "Mark as read" action on the GroupCard that marks the group and all its member articles as read without navigating to the Group_Detail_Screen.

### Requirement 4: Saved/Bookmarked Articles and Groups Page

**User Story:** As a reader, I want to save articles and groups for later reference and access them from a dedicated page, so that I can revisit important content even after it has been marked as read.

#### Acceptance Criteria

1. THE Reader_App SHALL provide a Saved_Articles_Page accessible from the Category_Selection_Screen navigation.
2. THE Reader_App SHALL display a save/bookmark button on the Article_Detail_Screen positioned next to the "Read Original" button.
3. THE Reader_App SHALL display a save/bookmark button on the Group_Detail_Screen.
4. WHEN the user taps the save button on an unsaved article or group, THE Reader_App SHALL add the item ID to the Saved_Items_Store in localStorage.
5. WHEN the user taps the save button on an already-saved article or group, THE Reader_App SHALL remove the item ID from the Saved_Items_Store in localStorage.
6. THE Saved_Articles_Page SHALL display all saved articles and groups regardless of their Read_State.
7. THE Saved_Articles_Page SHALL display saved items sorted by save date descending (most recently saved items first).
8. THE Reader_App SHALL fetch article and group data for saved items from the Article_API when the Saved_Articles_Page is displayed.
9. THE Reader_App SHALL allow the user to remove an article or group from the saved list directly from the Saved_Articles_Page.
10. THE save button SHALL visually indicate whether the current article or group is saved or unsaved.
11. THE Reader_App SHALL persist the Saved_Items_Store across browser sessions using localStorage.
12. IF a saved article or group no longer exists in the Article_API, THEN THE Reader_App SHALL display the item as unavailable with an option to remove it from the saved list.

### Requirement 5: Display Publication Time Alongside Date

**User Story:** As a reader, I want to see the publication time next to the date on article cards and detail views, so that I can understand when during the day an article was published.

#### Acceptance Criteria

1. THE Reader_App SHALL display the publication time (hours and minutes) alongside the publication date on each Article_Card.
2. THE Reader_App SHALL display the publication time alongside the publication date on the Article_Detail_Screen.
3. THE Reader_App SHALL display the publication time alongside the publication date on each GroupCard.
4. THE Reader_App SHALL format the publication time using the user's locale time format.
5. IF the `published_at` field is null, THEN THE Reader_App SHALL display neither date nor time for that article.

