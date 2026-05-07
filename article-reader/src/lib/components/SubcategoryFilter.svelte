<script lang="ts">
	interface Props {
		subcategories: string[];
		selected: string | null;
		onSelect: (subcategory: string | null) => void;
	}

	let { subcategories, selected, onSelect }: Props = $props();
</script>

{#if subcategories.length > 0}
	<div class="flex flex-wrap gap-2">
		<button
			onclick={() => onSelect(null)}
			class="rounded-full px-3 py-1 text-sm transition-colors {selected === null
				? 'bg-blue-600 text-white'
				: 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
		>
			All
		</button>
		{#each subcategories as subcategory}
			<button
				onclick={() => onSelect(subcategory)}
				class="rounded-full px-3 py-1 text-sm transition-colors {selected === subcategory
					? 'bg-blue-600 text-white'
					: 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
			>
				{subcategory}
			</button>
		{/each}
	</div>
{/if}
