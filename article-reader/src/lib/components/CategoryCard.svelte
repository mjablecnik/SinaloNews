<script lang="ts">
	import { goto } from '$app/navigation';

	interface Props {
		category: string;
		count: number;
	}

	let { category, count }: Props = $props();

	function navigate() {
		goto(`/category/${encodeURIComponent(category)}`);
	}
</script>

<button
	onclick={navigate}
	class="flex w-full flex-col gap-1 rounded-lg border border-gray-200 bg-white p-4 text-left shadow-sm hover:border-blue-300 hover:shadow-md transition-all"
>
	<span class="text-base font-semibold text-gray-900">{category}</span>
	<span class="text-sm text-gray-500">{count} {count === 1 ? 'article' : 'articles'}</span>
</button>
