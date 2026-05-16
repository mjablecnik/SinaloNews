<script lang="ts">
	import type { PageData } from './$types';
	import { invalidate } from '$app/navigation';
	import { navigating } from '$app/stores';
	import { onMount } from 'svelte';
	import type { CategoryCount } from '$lib/types';
	import CategoryCard from '$lib/components/CategoryCard.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	const ORDER_KEY = 'article-reader:category-order';

	let { data }: { data: PageData } = $props();
	let listContainer: HTMLDivElement | undefined = $state();
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

	// Touch drag support with long-press detection
	let touchStartY = $state(0);
	let touchDragIndex = $state<number | null>(null);
	let longPressTimer: ReturnType<typeof setTimeout> | null = null;
	let isDragging = $state(false);
	let pendingTouchIndex = $state<number | null>(null);

	function handleTouchStart(e: TouchEvent, index: number) {
		touchStartY = e.touches[0].clientY;
		isDragging = false;
		pendingTouchIndex = index;
		// Start long-press timer (500ms)
		longPressTimer = setTimeout(() => {
			touchDragIndex = index;
			isDragging = true;
			// Vibrate for haptic feedback if available
			if (navigator.vibrate) navigator.vibrate(50);
		}, 500);
	}

	function handleTouchMove(e: TouchEvent) {
		// If not yet in drag mode, cancel long-press if finger moved too much (scrolling)
		if (!isDragging) {
			const dy = Math.abs(e.touches[0].clientY - touchStartY);
			if (dy > 10 && longPressTimer) {
				clearTimeout(longPressTimer);
				longPressTimer = null;
				pendingTouchIndex = null;
			}
			return;
		}
		// In drag mode — prevent pull-to-refresh and scrolling
		e.preventDefault();
		e.stopPropagation();
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
		if (longPressTimer) {
			clearTimeout(longPressTimer);
			longPressTimer = null;
		}
		if (isDragging && touchDragIndex !== null && dragOverIndex !== null && touchDragIndex !== dragOverIndex) {
			const items = [...orderedCategories];
			const [moved] = items.splice(touchDragIndex, 1);
			items.splice(dragOverIndex, 0, moved);
			orderedCategories = items;
			saveOrder(items);
		}
		touchDragIndex = null;
		dragOverIndex = null;
		isDragging = false;
		pendingTouchIndex = null;
	}

	function reload() {
		invalidate('app:home');
	}

	// Register non-passive touchmove to allow preventDefault during drag
	onMount(() => {
		const handler = (e: TouchEvent) => {
			if (isDragging) {
				e.preventDefault();
			}
		};
		document.addEventListener('touchmove', handler, { passive: false });
		return () => document.removeEventListener('touchmove', handler);
	});
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<div class="mb-6 flex items-center justify-between">
		<h1 class="text-2xl font-bold text-gray-900">Article Reader</h1>
		<a
			href="/saved"
			class="flex items-center gap-1.5 rounded px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100"
		>
			<svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
			</svg>
			Saved
		</a>
	</div>

	{#if $navigating || loading}
		<LoadingSpinner />
	{:else if data.error}
		<ErrorMessage message={data.error} onRetry={reload} />
	{:else if orderedCategories.length === 0}
		<p class="py-12 text-center text-gray-500">No categories available.</p>
	{:else}
		<div class="flex flex-col gap-3">
			<a
				href="/category/__all__"
				class="flex flex-col gap-1 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-600 p-4 text-left shadow-md hover:shadow-lg transition-all"
			>
				<span class="text-base font-semibold text-white">All in one</span>
				<span class="text-sm text-blue-100">
					{data.totalCount} articles
				</span>
			</a>
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
					class="select-none transition-transform {dragOverIndex === i ? 'border-t-2 border-blue-400' : ''} {dragIndex === i || touchDragIndex === i ? 'opacity-50' : ''}"
				>
					<CategoryCard
						category={cat.category}
						count={cat.count}
					/>
				</div>
			{/each}
		</div>
	{/if}
</main>
