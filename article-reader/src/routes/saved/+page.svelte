<script lang="ts">
	import type { PageData } from './$types';
	import type { SavedItem } from './+page';
	import type { ArticleDetail, GroupDetail, FeedItem } from '$lib/types';
	import { savedItems } from '$lib/stores/savedItems';
	import { readState } from '$lib/stores/readState';
	import { groupReadState } from '$lib/stores/groupReadState';
	import ArticleCard from '$lib/components/ArticleCard.svelte';
	import GroupCard from '$lib/components/GroupCard.svelte';

	let { data }: { data: PageData } = $props();

	let visibleItems = $derived(
		(data.items as SavedItem[]).filter((item) => {
			if (item.type === 'article') return $savedItems.articles.includes(item.id);
			return $savedItems.groups.includes(item.id);
		})
	);

	function groupDetailToFeedItem(g: GroupDetail): FeedItem {
		return {
			type: 'group',
			id: g.id,
			title: g.title,
			summary: g.summary,
			category: g.category,
			importance_score: 0,
			tags: [],
			grouped_date: g.grouped_date,
			member_count: g.member_count
		};
	}
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<div class="mb-6 flex items-center gap-3">
		<a href="/" class="text-sm text-gray-500 hover:text-gray-700">← Back</a>
		<h1 class="text-2xl font-bold text-gray-900">Saved Items</h1>
	</div>

	{#if visibleItems.length === 0}
		<div class="py-16 text-center">
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="mx-auto mb-4 h-12 w-12 text-gray-300"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="1.5"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
			</svg>
			<p class="text-gray-500">No saved items yet.</p>
			<p class="mt-1 text-sm text-gray-400">Bookmark articles and groups to find them here.</p>
		</div>
	{:else}
		<div class="flex flex-col gap-3">
			{#each visibleItems as item (item.id + '-' + item.type)}
				{#if item.data === null}
					<div class="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
						<div>
							<p class="text-sm font-medium text-gray-500">
								{item.type === 'article' ? 'Article' : 'Group'} unavailable
							</p>
							<p class="text-xs text-gray-400">This item no longer exists.</p>
						</div>
						<button
							onclick={() =>
								item.type === 'article'
									? savedItems.removeArticle(item.id)
									: savedItems.removeGroup(item.id)}
							class="ml-4 rounded px-2 py-1 text-xs text-red-500 hover:bg-red-50 hover:text-red-700"
						>
							Remove
						</button>
					</div>
				{:else if item.type === 'article'}
					<div class="relative">
						<ArticleCard
							article={item.data as ArticleDetail}
							isRead={$readState.includes(item.id)}
						/>
						<button
							onclick={(e) => { e.stopPropagation(); savedItems.removeArticle(item.id); }}
							class="absolute right-2 top-2 z-10 rounded bg-white/80 px-2 py-0.5 text-xs text-red-400 shadow-sm hover:bg-red-50 hover:text-red-600"
							title="Remove from saved"
						>
							✕ Remove
						</button>
					</div>
				{:else}
					<div class="relative">
						<GroupCard
							group={groupDetailToFeedItem(item.data as GroupDetail)}
							isRead={$groupReadState.includes(item.id)}
						/>
						<button
							onclick={(e) => { e.stopPropagation(); savedItems.removeGroup(item.id); }}
							class="absolute right-2 top-2 z-10 rounded bg-white/80 px-2 py-0.5 text-xs text-red-400 shadow-sm hover:bg-red-50 hover:text-red-600"
							title="Remove from saved"
						>
							✕ Remove
						</button>
					</div>
				{/if}
			{/each}
		</div>
	{/if}
</main>
