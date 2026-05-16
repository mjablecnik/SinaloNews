<script lang="ts">
	import { goto } from '$app/navigation';

	const COLOR_PALETTE = [
		'bg-gradient-to-br from-emerald-500 to-teal-600',
		'bg-gradient-to-br from-rose-500 to-pink-600',
		'bg-gradient-to-br from-amber-500 to-orange-600',
		'bg-gradient-to-br from-violet-500 to-purple-600',
		'bg-gradient-to-br from-cyan-500 to-sky-600',
		'bg-gradient-to-br from-lime-500 to-green-600',
		'bg-gradient-to-br from-fuchsia-500 to-pink-600',
		'bg-gradient-to-br from-red-500 to-rose-600',
	];

	interface Props {
		category: string;
		count: number;
		unreadCount?: number;
		colorIndex?: number;
	}

	let { category, count, unreadCount, colorIndex }: Props = $props();

	function navigate() {
		goto(`/category/${encodeURIComponent(category)}`);
	}

	const colored = colorIndex !== undefined;
	const bgClasses = colored
		? COLOR_PALETTE[colorIndex % COLOR_PALETTE.length]
		: 'bg-white border border-gray-200';
	const textClass = colored ? 'text-white' : 'text-gray-900';
	const subtextClass = colored ? 'text-white/80' : 'text-gray-500';
</script>

<button
	onclick={navigate}
	class="flex w-full flex-col gap-1 rounded-lg p-4 text-left shadow-sm hover:shadow-md transition-all {bgClasses}"
>
	<span class="text-base font-semibold {textClass}">{category}</span>
	{#if unreadCount !== undefined}
		<span class="text-sm {subtextClass}">{unreadCount} unread / {count}</span>
	{:else}
		<span class="text-sm {subtextClass}">{count} {count === 1 ? 'article' : 'articles'}</span>
	{/if}
</button>
