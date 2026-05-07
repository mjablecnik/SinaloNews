<script lang="ts">
	import type { PageData } from './$types';
	import { invalidate } from '$app/navigation';
	import { navigating } from '$app/stores';
	import CategoryCard from '$lib/components/CategoryCard.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	let { data }: { data: PageData } = $props();
	let loading = $state(!data.categories.length && !data.error);

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
	{:else if data.categories.length === 0}
		<p class="py-12 text-center text-gray-500">No categories available.</p>
	{:else}
		<div class="grid gap-3 sm:grid-cols-2">
			{#each data.categories as cat}
				<CategoryCard category={cat.category} count={cat.count} />
			{/each}
		</div>
	{/if}
</main>
