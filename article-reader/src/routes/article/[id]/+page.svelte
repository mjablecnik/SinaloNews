<script lang="ts">
	import type { PageData } from './$types';
	import { onMount } from 'svelte';
	import { readState } from '$lib/stores/readState';
	import { formatExtractedText, sanitizeSummary } from '$lib/utils';
	import MarkdownRenderer from '$lib/components/MarkdownRenderer.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';

	let { data }: { data: PageData } = $props();

	onMount(() => {
		if (data.article) {
			readState.markAsRead(data.article.id);
		}
	});

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

	let formattedText = $derived(
		data.article?.extracted_text ? formatExtractedText(data.article.extracted_text) : ''
	);
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<button onclick={() => history.back()} class="mb-6 text-sm text-gray-500 hover:text-gray-700">
		← Back
	</button>

	{#if data.error}
		<ErrorMessage message={data.error} onRetry={() => history.back()} />
	{:else if data.article}
		{@const article = data.article}
		<article>
			<div class="mb-4 space-y-1">
				{#if article.title}
					<h1 class="text-xl font-bold text-gray-900">{article.title}</h1>
				{/if}
				<div class="flex flex-wrap gap-3 text-sm text-gray-500">
					{#if article.author}
						<span>{article.author}</span>
					{/if}
					{#if article.published_at}
						<span>{formatDate(article.published_at)}</span>
					{/if}
					<span class="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700">
						{article.importance_score}/10
					</span>
					{#if getSource(article.url)}
						<span class="text-gray-400">{getSource(article.url)}</span>
					{/if}
				</div>
			</div>

			{#if article.url}
				<a
					href={article.url}
					target="_blank"
					rel="noopener noreferrer"
					class="mb-6 inline-block rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 {!article.extracted_text
						? 'text-base font-semibold'
						: ''}"
				>
					Read Original ↗
				</a>
			{/if}

			{#if article.summary}
				<section class="mb-6">
					<h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Summary</h2>
					<div class="rounded-lg bg-gray-50 p-4">
						<MarkdownRenderer content={sanitizeSummary(article.summary, 10000)} />
					</div>
				</section>
			{/if}

			{#if article.extracted_text}
				<section>
					<h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
						Full Article
					</h2>
					<div class="prose max-w-none">
						<MarkdownRenderer content={formattedText} />
					</div>
				</section>
			{/if}
		</article>
	{/if}
</main>
