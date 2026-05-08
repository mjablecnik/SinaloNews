<script lang="ts">
	import type { PageData } from './$types';
	import { goto, invalidate } from '$app/navigation';
	import { readState } from '$lib/stores/readState';
	import ArticleCard from '$lib/components/ArticleCard.svelte';
	import GroupCard from '$lib/components/GroupCard.svelte';
	import SubcategoryFilter from '$lib/components/SubcategoryFilter.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import type { ArticleSummary } from '$lib/types';

	let { data }: { data: PageData } = $props();

	let selectedSubcategory = $state<string | null>(null);

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

	let filteredItems = $derived(
		selectedSubcategory
			? data.items.filter((item) =>
					item.tags.some(
						(t) => t.category === data.category && t.subcategory === selectedSubcategory
					)
				)
			: data.items
	);
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<div class="mb-6 flex items-center justify-between">
		<button onclick={() => goto('/')} class="text-sm text-gray-500 hover:text-gray-700">← Back</button>
		<h1 class="text-xl font-bold text-gray-900">{data.category}</h1>
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
		{#if subcategories.length > 0}
			<div class="mb-4">
				<SubcategoryFilter
					{subcategories}
					selected={selectedSubcategory}
					onSelect={(s) => { selectedSubcategory = s; }}
				/>
			</div>
		{/if}

		{#if filteredItems.length === 0}
			<p class="py-12 text-center text-gray-500">No articles found.</p>
		{:else}
			<div class="flex flex-col gap-3">
				{#each filteredItems as item}
					{#if item.type === 'group'}
						<GroupCard group={item} />
					{:else}
						<ArticleCard
							article={item as unknown as ArticleSummary}
							isRead={$readState.includes(item.id)}
							onMarkRead={(id) => readState.markAsRead(id)}
						/>
					{/if}
				{/each}
			</div>
		{/if}
	{/if}
</main>
