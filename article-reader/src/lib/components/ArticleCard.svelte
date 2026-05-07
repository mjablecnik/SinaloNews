<script lang="ts">
	import { goto } from '$app/navigation';
	import { marked } from 'marked';
	import type { ArticleSummary } from '$lib/types';
	import { sanitizeSummary } from '$lib/utils';

	const renderer = new marked.Renderer();
	renderer.link = ({ href, text }) => {
		return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-blue-600 underline">${text}</a>`;
	};

	interface Props {
		article: ArticleSummary;
		isRead: boolean;
		onMarkRead?: (id: number) => void;
	}

	let { article, isRead, onMarkRead }: Props = $props();

	function formatDate(dateStr: string | null): string {
		if (!dateStr) return '';
		return new Date(dateStr).toLocaleDateString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function getSource(url: string | null): string {
		if (!url) return '';
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return '';
		}
	}

	function navigate() {
		goto(`/article/${article.id}`);
	}

	let summaryHtml = $derived(
		article.summary ? (marked(sanitizeSummary(article.summary), { renderer }) as string) : ''
	);
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

	{#if summaryHtml}
		<div
			class="prose prose-sm max-w-none text-gray-800 {isRead ? '' : 'font-semibold'}"
			onclick={(e) => { if ((e.target as HTMLElement).tagName === 'A') e.stopPropagation(); }}
		>
			{@html summaryHtml}
		</div>
	{:else}
		<p class="text-sm leading-relaxed text-gray-800 {isRead ? '' : 'font-semibold'}">
			{article.title ?? '(No summary)'}
		</p>
	{/if}

	<div class="flex flex-wrap items-center gap-3 text-xs text-gray-500">
		{#if article.published_at}
			<span>{formatDate(article.published_at)}</span>
		{/if}
		<span class="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700">
			{article.importance_score}/10
		</span>
		{#if getSource(article.url)}
			<span class="text-gray-400">{getSource(article.url)}</span>
		{/if}
		{#if !isRead && onMarkRead}
			<button
				onclick={(e) => { e.stopPropagation(); onMarkRead(article.id); }}
				class="ml-auto rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-200 hover:text-gray-700"
				title="Mark as read"
			>
				✓ Read
			</button>
		{/if}
	</div>
</button>
