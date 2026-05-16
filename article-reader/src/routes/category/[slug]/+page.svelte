<script lang="ts">
	import type { PageData } from './$types';
	import { goto, invalidate, beforeNavigate } from '$app/navigation';
	import { readState } from '$lib/stores/readState';
	import { groupReadState } from '$lib/stores/groupReadState';
	import { sessionReadSet } from '$lib/stores/sessionReadSet';
	import { settings } from '$lib/stores/settings';
	import { getFeed } from '$lib/api';
	import { buildDateFrom } from '$lib/utils';
	import { getCachedFeed, setCachedFeed, clearFeedCache } from '$lib/stores/feedCache';
	import ArticleCard from '$lib/components/ArticleCard.svelte';
	import GroupCard from '$lib/components/GroupCard.svelte';
	import DateFilter from '$lib/components/DateFilter.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import { sortByImportance, filterReadItems } from '$lib/utils';
	import type { ArticleSummary, FeedItem } from '$lib/types';
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';

	let { data }: { data: PageData } = $props();

	const isAllInOne = $derived(data.category === '__all__');

	// Generate all date buttons from daysBack setting
	let dates = $derived.by(() => {
		const s = get(settings);
		const days: string[] = [];
		const today = new Date();
		for (let i = 0; i < s.daysBack; i++) {
			const d = new Date(today);
			d.setDate(today.getDate() - i);
			days.push(d.toISOString().split('T')[0]);
		}
		return days;
	});

	// Pagination state
	let allItems = $state<FeedItem[]>([]);
	let currentPage = $state(1);
	let totalPages = $state(0);
	let totalCount = $state(0);
	let isLoadingMore = $state(false);
	let isLoadingDate = $state(false);
	let loadError = $state<string | null>(null);

	// Persist selected date in sessionStorage
	const FILTER_KEY = `article-reader:date-filter:${data.category}`;

	function loadSavedDate(): string | null {
		if (typeof sessionStorage === 'undefined') return null;
		return sessionStorage.getItem(FILTER_KEY);
	}

	function saveDateFilter(date: string | null) {
		if (typeof sessionStorage === 'undefined') return;
		if (date === null) {
			sessionStorage.removeItem(FILTER_KEY);
		} else {
			sessionStorage.setItem(FILTER_KEY, date);
		}
	}

	let selectedDate = $state<string | null>(loadSavedDate());

	// Save current state to in-memory cache
	function saveToCache() {
		setCachedFeed(data.category, selectedDate, {
			items: allItems,
			currentPage,
			totalPages,
			totalCount,
			selectedDate
		});
	}

	// Try to restore from cache on mount
	onMount(() => {
		const savedDate = loadSavedDate();
		const cached = getCachedFeed(data.category, savedDate);

		if (cached) {
			// Restore from in-memory cache — no network requests needed
			allItems = cached.items;
			currentPage = cached.currentPage;
			totalPages = cached.totalPages;
			totalCount = cached.totalCount;
			selectedDate = cached.selectedDate;
		} else if (savedDate !== null) {
			// Date filter saved but no cache — fetch for that date
			selectDate(savedDate);
		} else {
			// No cache, no saved date — use data from +page.ts (already set by $effect)
			allItems = [...data.items];
			currentPage = data.currentPage;
			totalPages = data.totalPages;
			totalCount = data.totalCount;
		}

		if (!sentinelEl) return;
		const observer = new IntersectionObserver(
			(entries) => {
				if (entries[0].isIntersecting && hasMore && !isLoadingMore) {
					loadMore();
				}
			},
			{ rootMargin: '200px' }
		);
		observer.observe(sentinelEl);
		return () => observer.disconnect();
	});

	let visibleItems = $derived(filterReadItems(allItems, $readState, $groupReadState, $sessionReadSet));

	let filteredItems = $derived(sortByImportance(visibleItems));

	let unreadCount = $derived(
		filteredItems.filter((item) => {
			const key = `${item.type}:${item.id}`;
			if ($sessionReadSet.has(key)) {
				if (item.type === 'group') return !$groupReadState.includes(item.id);
				return !$readState.includes(item.id);
			}
			return true;
		}).length
	);

	let hasMore = $derived(currentPage < totalPages);

	function buildFeedParams(page: number) {
		const s = get(settings);
		return {
			...(isAllInOne ? {} : { category: data.category }),
			min_score: s.minScore,
			date_from: selectedDate ?? buildDateFrom(s.daysBack),
			...(selectedDate ? { date_to: selectedDate } : {}),
			page,
			size: data.pageSize
		};
	}

	async function selectDate(date: string | null) {
		selectedDate = date;
		saveDateFilter(date);

		// Check cache first
		const cached = getCachedFeed(data.category, date);
		if (cached) {
			allItems = cached.items;
			currentPage = cached.currentPage;
			totalPages = cached.totalPages;
			totalCount = cached.totalCount;
			return;
		}

		isLoadingDate = true;
		loadError = null;
		try {
			const response = await getFeed(buildFeedParams(1));
			allItems = [...response.items];
			currentPage = 1;
			totalPages = response.pages;
			totalCount = response.total;
			saveToCache();
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load items';
			allItems = [];
			currentPage = 1;
			totalPages = 0;
			totalCount = 0;
		} finally {
			isLoadingDate = false;
		}
	}

	async function loadMore() {
		if (isLoadingMore || !hasMore) return;
		isLoadingMore = true;
		loadError = null;
		try {
			const nextPage = currentPage + 1;
			const response = await getFeed(buildFeedParams(nextPage));
			allItems = [...allItems, ...response.items];
			currentPage = nextPage;
			totalPages = response.pages;
			saveToCache();
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load more items';
		} finally {
			isLoadingMore = false;
		}
	}

	// Infinite scroll sentinel
	let sentinelEl: HTMLDivElement | undefined = $state();

	beforeNavigate(({ to }) => {
		const path = to?.url.pathname ?? '';
		const articleMatch = path.match(/^\/article\/(\d+)$/);
		const groupMatch = path.match(/^\/group\/(\d+)$/);

		if (articleMatch) {
			const id = parseInt(articleMatch[1]);
			readState.markAsRead(id);
			sessionReadSet.add('article', id);
			// Save to cache before leaving
			saveToCache();
		} else if (groupMatch) {
			const id = parseInt(groupMatch[1]);
			sessionReadSet.add('group', id);
			// Save to cache before leaving
			saveToCache();
		} else {
			// Navigating away from category — clear cache and filters
			saveDateFilter(null);
			clearFeedCache(data.category);
			sessionReadSet.clear();
		}
	});
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<div class="mb-6 flex items-center justify-between">
		<button onclick={() => goto('/')} class="text-sm text-gray-500 hover:text-gray-700">← Back</button>
		<h1 class="text-xl font-bold text-gray-900">{isAllInOne ? 'All in one' : data.category}</h1>
		<div class="flex items-center gap-2">
			<button onclick={() => invalidate('app:category')} class="rounded px-3 py-1 text-sm text-gray-600 hover:bg-gray-100" title="Reload">
				↻ Reload
			</button>
			<a href="/settings" class="rounded px-3 py-1 text-sm text-gray-600 hover:bg-gray-100" title="Settings">
				⚙ Settings
			</a>
		</div>
	</div>

	{#if data.error}
		<ErrorMessage message={data.error} onRetry={() => location.reload()} />
	{:else}
		<div class="mb-4">
			<DateFilter {dates} selected={selectedDate} onSelect={selectDate} />
			<p class="mt-2 text-xs text-gray-500">{unreadCount} unread · {totalCount} total</p>
		</div>

		{#if isLoadingDate}
			<LoadingSpinner />
		{:else if filteredItems.length === 0 && !isLoadingMore}
			<p class="py-12 text-center text-gray-500">
				{selectedDate ? 'No articles for this date.' : 'No articles found.'}
			</p>
		{:else}
			<div class="flex flex-col gap-3">
				{#each filteredItems as item}
					{#if item.type === 'group'}
						<GroupCard
							group={item}
							isRead={$groupReadState.includes(item.id) || $sessionReadSet.has(`group:${item.id}`)}
							onMarkRead={(id) => {
								groupReadState.markGroupAsRead(id, []);
								sessionReadSet.add('group', id);
							}}
						/>
					{:else}
						<ArticleCard
							article={item as unknown as ArticleSummary}
							isRead={$readState.includes(item.id) || $sessionReadSet.has(`article:${item.id}`)}
							onMarkRead={(id) => {
								readState.markAsRead(id);
								sessionReadSet.add('article', id);
							}}
						/>
					{/if}
				{/each}
			</div>

			<!-- Infinite scroll sentinel -->
			<div bind:this={sentinelEl} class="py-4">
				{#if isLoadingMore}
					<div class="flex justify-center">
						<LoadingSpinner />
					</div>
				{:else if hasMore}
					<button
						onclick={loadMore}
						class="w-full rounded-lg border border-gray-200 bg-white py-3 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
					>
						Load more
					</button>
				{:else if allItems.length > 0}
					<p class="text-center text-xs text-gray-400">All items loaded</p>
				{/if}
			</div>

			{#if loadError}
				<div class="mt-2 rounded bg-red-50 p-3 text-sm text-red-700">
					{loadError}
					<button onclick={loadMore} class="ml-2 underline">Retry</button>
				</div>
			{/if}
		{/if}
	{/if}
</main>
