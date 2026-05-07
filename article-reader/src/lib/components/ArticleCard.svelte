<script lang="ts">
	import { goto } from '$app/navigation';
	import type { ArticleSummary } from '$lib/types';

	interface Props {
		article: ArticleSummary;
		isRead: boolean;
	}

	let { article, isRead }: Props = $props();

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '';
		return new Date(dateStr).toLocaleDateString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function navigate() {
		goto(`/article/${article.id}`);
	}
</script>

<button
	onclick={navigate}
	class="flex w-full flex-col gap-2 rounded-lg border bg-white p-4 text-left shadow-sm hover:shadow-md transition-all {isRead
		? 'border-gray-100'
		: 'border-blue-200'}"
>
	{#if !isRead}
		<span class="inline-block h-2 w-2 rounded-full bg-blue-500" aria-label="Unread"></span>
	{/if}

	<p class="text-sm leading-relaxed text-gray-800 {isRead ? '' : 'font-semibold'}">
		{article.summary ?? article.title ?? '(No summary)'}
	</p>

	<div class="flex items-center gap-3 text-xs text-gray-500">
		{#if article.published_at}
			<span>{formatDate(article.published_at)}</span>
		{/if}
		<span class="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700">
			{article.importance_score}/10
		</span>
	</div>
</button>
