<script lang="ts">
	import type { PageData } from './$types';
	import { invalidate, goto } from '$app/navigation';
	import { navigating } from '$app/stores';
	import type { CategoryCount } from '$lib/types';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	const ORDER_KEY = 'article-reader:category-order';

	let { data }: { data: PageData } = $props();
	let loading = $state(!data.categories.length && !data.error);

	function getOrderedCategories(categories: CategoryCount[]): CategoryCount[] {
		if (typeof localStorage === 'undefined') return categories;
		try {
			const raw = localStorage.getItem(ORDER_KEY);
			if (!raw) return categories;
			const order: string[] = JSON.parse(raw);
			const map = new Map(categories.map((c) => [c.category, c]));
			const ordered: CategoryCount[] = [];
			for (const name of order) {
				const cat = map.get(name);
				if (cat) {
					ordered.push(cat);
					map.delete(name);
				}
			}
			for (const cat of map.values()) {
				ordered.push(cat);
			}
			return ordered;
		} catch {
			return categories;
		}
	}

	function saveOrder(categories: CategoryCount[]) {
		if (typeof localStorage === 'undefined') return;
		localStorage.setItem(ORDER_KEY, JSON.stringify(categories.map((c) => c.category)));
	}

	let orderedCategories = $state<CategoryCount[]>([]);
	$effect(() => {
		orderedCategories = getOrderedCategories(data.categories);
	});

	function moveUp(index: number) {
		if (index <= 0) return;
		const items = [...orderedCategories];
		[items[index - 1], items[index]] = [items[index], items[index - 1]];
		orderedCategories = items;
		saveOrder(items);
	}

	function moveDown(index: number) {
		if (index >= orderedCategories.length - 1) return;
		const items = [...orderedCategories];
		[items[index], items[index + 1]] = [items[index + 1], items[index]];
		orderedCategories = items;
		saveOrder(items);
	}

	let editMode = $state(false);

	function reload() {
		invalidate('app:home');
	}
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<div class="mb-6 flex items-center justify-between">
		<h1 class="text-2xl font-bold text-gray-900">Article Reader</h1>
		{#if orderedCategories.length > 0}
			<button
				onclick={() => { editMode = !editMode; }}
				class="rounded px-3 py-1 text-sm {editMode ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'}"
			>
				{editMode ? '✓ Done' : '↕ Reorder'}
			</button>
		{/if}
	</div>

	{#if $navigating || loading}
		<LoadingSpinner />
	{:else if data.error}
		<ErrorMessage message={data.error} onRetry={reload} />
	{:else if orderedCategories.length === 0}
		<p class="py-12 text-center text-gray-500">No categories available.</p>
	{:else}
		<div class="flex flex-col gap-3">
			{#each orderedCategories as cat, i}
				<div class="flex items-center gap-2">
					{#if editMode}
						<div class="flex flex-col gap-0.5">
							<button
								onclick={() => moveUp(i)}
								disabled={i === 0}
								class="rounded px-1.5 py-0.5 text-xs text-gray-500 hover:bg-gray-200 disabled:opacity-30"
							>▲</button>
							<button
								onclick={() => moveDown(i)}
								disabled={i === orderedCategories.length - 1}
								class="rounded px-1.5 py-0.5 text-xs text-gray-500 hover:bg-gray-200 disabled:opacity-30"
							>▼</button>
						</div>
					{/if}
					<button
						onclick={() => goto(`/category/${encodeURIComponent(cat.category)}`)}
						class="flex flex-1 items-center justify-between rounded-lg border border-gray-200 bg-white p-4 text-left shadow-sm hover:border-blue-300 hover:shadow-md transition-all"
					>
						<span class="text-base font-semibold text-gray-900">{cat.category}</span>
						<span class="text-sm text-gray-500">{cat.count}</span>
					</button>
				</div>
			{/each}
		</div>
	{/if}
</main>
