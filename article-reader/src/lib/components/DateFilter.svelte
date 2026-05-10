<script lang="ts">
	interface Props {
		dates: string[];
		selected: string | null;
		onSelect: (date: string | null) => void;
	}

	let { dates, selected, onSelect }: Props = $props();

	function formatChipDate(dateStr: string): string {
		const date = new Date(dateStr + 'T00:00:00');
		return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
	}
</script>

<div class="flex gap-2 overflow-x-auto pb-2 scrollbar-none">
	{#each dates as date}
		<button
			onclick={() => onSelect(date)}
			class="shrink-0 rounded-full px-3 py-1 text-sm font-medium transition-colors {selected === date
				? 'bg-blue-600 text-white'
				: 'bg-gray-100 text-gray-700 hover:bg-gray-200'}"
		>
			{formatChipDate(date)}
		</button>
	{/each}
</div>
