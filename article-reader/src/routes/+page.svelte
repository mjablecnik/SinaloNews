<script lang="ts">
	import type { PageData } from './$types';
	import { invalidate } from '$app/navigation';
	import { navigating } from '$app/stores';
	import type { CategoryCount } from '$lib/types';
	import CategoryCard from '$lib/components/CategoryCard.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	const ORDER_KEY = 'article-reader:category-order';

	let { data }: { data: PageData } = $props();
	let loading = $state(!data.categories.length && !data.error);

	// Apply saved order to categories
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
			// Append any new categories not in saved order
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

	// Drag and drop state
	let dragIndex = $state<number | null>(null);
	let dragOverIndex = $state<number | null>(null);

	function handleDragStart(index: number) {
		dragIndex = index;
	}

	function handleDragOver(e: DragEvent, index: number) {
		e.preventDefault();
		dragOverIndex = index;
	}

	function handleDrop(index: number) {
		if (dragIndex === null || dragIndex === index) {
			dragIndex = null;
			dragOverIndex = null;
			return;
		}
		const items = [...orderedCategories];
		const [moved] = items.splice(dragIndex, 1);
		items.splice(index, 0, moved);
		orderedCategories = items;
		saveOrder(items);
		dragIndex = null;
		dragOverIndex = null;
	}

	function handleDragEnd() {
		dragIndex = null;
		dragOverIndex = null;
	}

	// Touch drag support
	let touchStartY = $state(0);
	let touchDragIndex = $state<number | null>(null);

	function handleTouchStart(e: TouchEvent, index: number) {
		touchStartY = e.touches[0].clientY;
		touchDragIndex = index;
	}

	function handleTouchMove(e: TouchEvent) {
		if (touchDragIndex === null) return;
		e.preventDefault();
		const touch = e.touches[0];
		const elements = document.querySelectorAll('[data-cat-index]');
		for (const el of elements) {
			const rect = el.getBoundingClientRect();
			if (touch.clientY >= rect.top && touch.clientY <= rect.bottom) {
				const idx = parseInt(el.getAttribute('data-cat-index') ?? '-1');
				if (idx >= 0 && idx !== touchDragIndex) {
					dragOverIndex = idx;
				}
				break;
			}
		}
	}

	function handleTouchEnd() {
		if (touchDragIndex !== null && dragOverIndex !== null && touchDragIndex !== dragOverIndex) {
			const items = [...orderedCategories];
			const [moved] = items.splice(touchDragIndex, 1);
			items.splice(dragOverIndex, 0, moved);
			orderedCategories = items;
			saveOrder(items);
		}
		touchDragIndex = null;
		dragOverIndex = null;
	}

	function reload() {
		invalidate('app:home');
	}
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<h1 class="mb-6 text-2xl font-bold text-gray-900">Article Reader</h1>

	{#if $navigating || loading}
		<LoadingSpinner />
	{:else if data.error}
		<ErrorMessage message={data.error} onRetry={reload} />
	{:else if orderedCategories.length === 0}
		<p class="py-12 text-center text-gray-500">No categories available.</p>
	{:else}
		<div class="flex flex-col gap-3">
			{#each orderedCategories as cat, i}
				<div
					data-cat-index={i}
					draggable="true"
					ondragstart={() => handleDragStart(i)}
					ondragover={(e) => handleDragOver(e, i)}
					ondrop={() => handleDrop(i)}
					ondragend={handleDragEnd}
					ontouchstart={(e) => handleTouchStart(e, i)}
					ontouchmove={(e) => handleTouchMove(e)}
					ontouchend={handleTouchEnd}
					class="select-none touch-none transition-transform {dragOverIndex === i ? 'border-t-2 border-blue-400' : ''} {dragIndex === i || touchDragIndex === i ? 'opacity-50' : ''}"
				>
					<CategoryCard category={cat.category} count={cat.count} />
				</div>
			{/each}
		</div>
	{/if}
</main>
