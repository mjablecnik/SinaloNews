<script lang="ts">
	import type { PageData } from './$types';
	import { goto, invalidate, beforeNavigate } from '$app/navigation';
	import { readState } from '$lib/stores/readState';
	import { groupReadState } from '$lib/stores/groupReadState';
	import { sessionReadSet } from '$lib/stores/sessionReadSet';
	import ArticleCard from '$lib/components/ArticleCard.svelte';
	import GroupCard from '$lib/components/GroupCard.svelte';
	import SubcategoryFilter from '$lib/components/SubcategoryFilter.svelte';
	import DateFilter from '$lib/components/DateFilter.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import { extractUniqueDates, getTodayDateString, sortByImportance, formatDateOnly, filterReadItems } from '$lib/utils';
	import type { ArticleSummary } from '$lib/types';

	let { data }: { data: PageData } = $props();

	const isAllInOne = $derived(data.category === '__all__');

	let selectedSubcategory = $state<string | null>(null);
	let selectedDate = $state<string | null>(getTodayDateString());

	let subcategories = $derived.by(() => {
		const seen = new Set<string>();
		for (const item of data.items) {
			for (const tag of item.tags) {
				if (tag.category === data.category && tag.subcategory) {
					seen.add(tag.subcategory);
				}
			}
		}
		return Array.from(seen);
	});

	let dates = $derived(extractUniqueDates(data.items));

	let visibleItems = $derived(filterReadItems(data.items, $readState, $groupReadState, $sessionReadSet));

	let filteredItems = $derived.by(() => {
		if (isAllInOne) {
			const sorted = sortByImportance(visibleItems);
			if (!selectedDate) return sorted;
			return sorted.filter((item) => {
				const dateStr = item.published_at ?? item.grouped_date;
				if (!dateStr) return false;
				return formatDateOnly(dateStr) === selectedDate;
			});
		}
		return selectedSubcategory
			? visibleItems.filter((item) =>
					item.tags.some(
						(t) => t.category === data.category && t.subcategory === selectedSubcategory
					)
				)
			: visibleItems;
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
		{#if isAllInOne}
			{#if dates.length > 0}
				<div class="mb-4">
					<DateFilter {dates} selected={selectedDate} onSelect={(d) => { selectedDate = d; }} />
				</div>
			{/if}
		{:else if subcategories.length > 0}
			<div class="mb-4">
				<SubcategoryFilter
					{subcategories}
					selected={selectedSubcategory}
					onSelect={(s) => { selectedSubcategory = s; }}
				/>
			</div>
		{/if}

		{#if filteredItems.length === 0}
			<p class="py-12 text-center text-gray-500">
				{isAllInOne && selectedDate ? 'No articles for this date.' : 'No articles found.'}
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
		{/if}
	{/if}
</main>
