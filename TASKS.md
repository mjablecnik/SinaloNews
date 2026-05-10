# TASKS

- [x] 1. [HIGH] Add `sortByImportance` function to `src/lib/utils.ts` that sorts FeedItem[] by `importance_score` descending
- [x] 2. [HIGH] Update `filteredItems` in `src/routes/category/[slug]/+page.svelte` to sort by importance (not date-then-importance) when `isAllInOne` is true
- [ ] 3. [HIGH] Replace `SubcategoryFilter` with `DateFilter` in category pages — remove subcategory filtering logic, add date filtering with `selectedDate` defaulting to today
- [ ] 4. [HIGH] Update `filteredItems` derived for non-"All in One" categories to filter by selected date instead of subcategory
- [ ] 5. [MEDIUM] Update `CategoryCard.svelte` to accept a `color` prop (gradient classes or style) and render with colored background instead of white
- [ ] 6. [MEDIUM] Create a deterministic color assignment utility (hash category name → palette index) in `src/lib/utils.ts`
- [ ] 7. [MEDIUM] Update `src/routes/+page.svelte` to pass a color to each `CategoryCard` based on category name
- [ ] 8. [MEDIUM] Modify `CategoryCard.svelte` to show only unread count (remove "read" and "total" display)
- [ ] 9. [MEDIUM] Update `src/routes/+page.svelte` to pass only `unreadCount` to `CategoryCard` (remove `readCount` and `count` from template)
- [ ] 10. [MEDIUM] Add optional `unreadCounts` prop (`Record<string, number>`) to `DateFilter.svelte` and display count on each date chip
- [ ] 11. [MEDIUM] Compute per-day unread counts in `src/routes/category/[slug]/+page.svelte` and pass to `DateFilter`
- [ ] 12. [LOW] Verify Tailwind purging works with the color palette (use full class strings in a safelist or lookup object)
