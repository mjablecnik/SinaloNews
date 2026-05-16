<script lang="ts">
	import { goto } from '$app/navigation';
	import { marked } from 'marked';
	import type { FeedItem, Tag } from '$lib/types';
	import { sanitizeSummary, formatDateTime } from '$lib/utils';

	interface Props {
		group: FeedItem;
		isRead?: boolean;
		onMarkRead?: (id: number) => void;
	}

	let { group, isRead = false, onMarkRead }: Props = $props();

	function navigate() {
		goto(`/group/${group.id}`);
	}

	let summaryHtml = $derived(
		group.summary ? (marked.parse(sanitizeSummary(group.summary)) as string) : ''
	);
</script>

<button
	onclick={navigate}
	class="relative flex w-full flex-col gap-2 rounded-lg border bg-white p-4 text-left shadow-sm hover:shadow-md transition-all {isRead
		? 'border-purple-100'
		: 'border-purple-200'}"
>
	<!-- Stacked card visual indicator -->
	<span
		class="absolute -bottom-1.5 left-2 right-2 h-full rounded-lg border border-purple-100 bg-purple-50 -z-10"
	></span>
	<span
		class="absolute -bottom-3 left-4 right-4 h-full rounded-lg border border-purple-50 bg-purple-50 -z-20"
	></span>

	{#if !isRead}
		<span class="inline-block h-2 w-2 rounded-full bg-blue-500" aria-label="Unread"></span>
	{/if}

	<div class="flex items-start gap-2">
		<span class="mt-0.5 text-purple-500" title="Article group" aria-label="Article group">
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="h-4 w-4 flex-shrink-0"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
				/>
			</svg>
		</span>
		<p class="text-sm font-semibold leading-snug text-gray-900">
			{group.title ?? '(No title)'}
		</p>
	</div>

	{#if summaryHtml}
		<div class="prose prose-sm max-w-none text-gray-700">
			{@html summaryHtml}
		</div>
	{/if}

	<div class="flex flex-wrap items-center gap-3 text-xs text-gray-500">
		{#if group.grouped_date}
			<span>{formatDateTime(group.grouped_date)}</span>
		{/if}
		<span class="rounded bg-purple-100 px-1.5 py-0.5 font-medium text-purple-700">
			{group.importance_score}/10
		</span>
		{#if group.member_count}
			<span class="rounded bg-gray-100 px-1.5 py-0.5 text-gray-600">
				{group.member_count} articles
			</span>
		{/if}
		{#if !isRead && onMarkRead}
			<button
				onclick={(e) => { e.stopPropagation(); onMarkRead(group.id); }}
				class="ml-auto rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-200 hover:text-gray-700"
				title="Mark as read"
			>
				✓ Read
			</button>
		{/if}
	</div>
</button>
