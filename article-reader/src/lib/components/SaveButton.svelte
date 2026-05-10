<script lang="ts">
	interface Props {
		isSaved: boolean;
		onToggle: () => void;
	}

	let { isSaved, onToggle }: Props = $props();
</script>

<button
	onclick={onToggle}
	class="inline-flex items-center gap-1.5 rounded px-3 py-2 text-sm transition-colors {isSaved
		? 'bg-amber-100 text-amber-700 hover:bg-amber-200'
		: 'bg-gray-100 text-gray-600 hover:bg-gray-200'}"
	title={isSaved ? 'Remove from saved' : 'Save for later'}
>
	{#if isSaved}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			class="h-4 w-4"
			viewBox="0 0 24 24"
			fill="currentColor"
		>
			<path d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
		</svg>
		Saved
	{:else}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			class="h-4 w-4"
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="2"
		>
			<path stroke-linecap="round" stroke-linejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
		</svg>
		Save
	{/if}
</button>
