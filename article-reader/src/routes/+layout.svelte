<script lang="ts">
	import '../app.css';
	import { navigating } from '$app/stores';
	import LoadingSpinner from '$lib/components/LoadingSpinner.svelte';

	let { children } = $props();
</script>

<div class="min-h-screen bg-gray-50">
	{#if $navigating}
		<LoadingSpinner />
	{/if}
	{@render children()}
</div>
