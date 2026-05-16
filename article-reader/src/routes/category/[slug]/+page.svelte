<script lang="ts">
	import type { PageData } from './$types';
	import { goto, invalidate, beforeNavigate } from '$app/navigation';
	import { readState } from '$lib/stores/readState';
	import { groupReadState } from '$lib/stores/groupReadState';
	import { sessionReadSet } from '$lib/stores/sessionReadSet';
	import { settings } from '$lib/stores/settings';
	import { getFeed } from '$lib/api';
	import { buildDateFrom } from '$lib/utils';
	import ArticleCard from '$lib/components/ArticleCard.svelte';
	import GroupCard from '$lib/components/GroupCard.svelte';
	import DateFilter from '$lib/components/DateFilter.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';
	import { extractUniqueDates, getTodayDateString, sortByImportance, formatDateOnly, filterReadItems } from '$lib/utils';
	import type { ArticleSummary, FeedItem } from '$lib/types';
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';

	let { data }: { data: PageData } = $props();

	const isAllInOne = $derived(data.category === '__all__');

	// Pagination state
	let allItems = $state<FeedItem[]>([]);
	let currentPage = $state(1);
	let totalPages = $state(0);
	let isLoadingMore = $state(false);
	let loadError = $state<string | null>(null);

	// Reset when data changes (e.g., navigation to different category)
	$effect(() => {
		allItems = [...data.items];
		currentPage = data.currentPage;
		totalPages = data.totalPages;
		loadError = null;
	});

	let selectedDate = $state<string | null>(getTodayDateString());

	let dates = $derived(extractUniqueDates(allItems));

	let visibleItems = $derived(filterReadItems(allItems, $readState, $groupReadState, $sessionReadSet));

	let filteredItems = $derived.by(() => {
		const sorted = sortByImportance(visibleItems);
		if (!selectedDate) return sorted;
		return sorted.filter((item) => {
			const dateStr = item.published_at ?? item.grouped_date;
			if (!dateStr) return false;
			return formatDateOnly(dateStr) === selectedDate;
		});
	});

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

	async function loadMore() {
		if (isLoadingMore || !hasMore) return;
		isLoadingMore = true;
		loadError = null;
		try {
			const s = get(settings);
			const nextPage = currentPage + 1;
			const feedParams = {
				...(isAllInOne ? {} : { category: data.category }),
				min_score: s.minScore,
				date_from: buildDateFrom(s.daysBack),
				page: nextPage,
				size: data.pageSize
			};
			const response = await getFeed(feedParams);
			allItems = [...allItems, ...response.items];
			currentPage = nextPage;
			totalPages = response.pages;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'Failed to load more items';
		} finally {
			isLoadingMore = false;
		}
	}

	// Infinite scroll: observe a sentinel element near the bottom
	let sentinelEl: HTMLDivElement | undefined = $state();

	onMount(() => {
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

	beforeNavigate(({ to }) => {
		const path = to?.url.pathname ?? '';
		const articleMatch = path.match(/^\/article\/(\d+)$/);
		const groupMatch = path.match(/^\/group\/(\d+)$/);

		if (articleMatch) {
			const id = parseInt(articleMatch[1]);
			readState.markAsRead(id);
			sessionReadSet.add('article', id);
		} else if (groupMatch) {
			const id = parseInt(groupMatch[1]);
			sessionReadSet.add('group', id);
		} else {
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
		{#if dates.length > 0}
			<div class="mb-4">
				<DateFilter {dates} selected={selectedDate} onSelect={(d) => { selectedDate = d; }} />
				<p class="mt-2 text-xs text-gray-500">{unreadCount} unread · {data.totalCount} total</p>
			</div>
		{/if}

		{#if filteredItems.length === 0 && !isLoadingMore}
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
