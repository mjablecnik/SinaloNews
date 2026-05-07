<script lang="ts">
	import type { PageData } from './$types';
	import { goto } from '$app/navigation';
	import { extractSubcategories } from '$lib/utils';
	import { readState } from '$lib/stores/readState';
	import ArticleCard from '$lib/components/ArticleCard.svelte';
	import SubcategoryFilter from '$lib/components/SubcategoryFilter.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';

	let { data }: { data: PageData } = $props();

	let selectedSubcategory = $state<string | null>(null);

	let subcategories = $derived(extractSubcategories(data.articles, data.category));

	let filteredArticles = $derived(
		selectedSubcategory
			? data.articles.filter((a) =>
					a.tags.some(
						(t) => t.category === data.category && t.subcategory === selectedSubcategory
					)
				)
			: data.articles
	);
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<div class="mb-6 flex items-center justify-between">
		<button onclick={() => goto('/')} class="text-sm text-gray-500 hover:text-gray-700">← Back</button>
		<h1 class="text-xl font-bold text-gray-900">{data.category}</h1>
		<a href="/settings" class="rounded px-3 py-1 text-sm text-gray-600 hover:bg-gray-100" title="Settings">
			⚙ Settings
		</a>
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

		{#if filteredArticles.length === 0}
			<p class="py-12 text-center text-gray-500">No articles found.</p>
		{:else}
			<div class="flex flex-col gap-3">
				{#each filteredArticles as article}
					<ArticleCard {article} isRead={$readState.includes(article.id)} />
				{/each}
			</div>
		{/if}
	{/if}
</main>
