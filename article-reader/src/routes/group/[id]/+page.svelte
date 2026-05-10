<script lang="ts">
	import type { PageData } from './$types';
	import { onMount } from 'svelte';
	import { groupReadState } from '$lib/stores/groupReadState';
	import MarkdownRenderer from '$lib/components/MarkdownRenderer.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';

	let { data }: { data: PageData } = $props();

	onMount(() => {
		if (data.group) {
			groupReadState.markGroupAsRead(
				data.group.id,
				data.group.members.map((m) => m.id)
			);
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
</script>

<main class="container mx-auto max-w-2xl px-4 py-8">
	<button onclick={() => history.back()} class="mb-6 text-sm text-gray-500 hover:text-gray-700">
		← Back
	</button>

	{#if data.error}
		<ErrorMessage message={data.error} onRetry={() => history.back()} />
	{:else if data.group}
		{@const group = data.group}
		<article>
			<div class="mb-4 space-y-1">
				<div class="flex items-center gap-2">
					<span class="rounded bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-700">
						Group · {group.member_count} articles
					</span>
					<span class="text-sm text-gray-500">{formatDate(group.grouped_date)}</span>
				</div>
				<h1 class="text-xl font-bold text-gray-900">{group.title}</h1>
			</div>

			<section class="mb-6">
				<h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Summary</h2>
				<div class="rounded-lg bg-gray-50 p-4">
					<p class="text-gray-700">{group.summary}</p>
				</div>
			</section>

			<section class="mb-8">
				<h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
					Full Article
				</h2>
				<div class="prose max-w-none">
					<MarkdownRenderer content={group.detail} />
				</div>
			</section>

			<section>
				<h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
					Sources ({group.member_count})
				</h2>
				<ul class="space-y-2">
					{#each group.members as member}
						<li>
							<a
								href="/article/{member.id}"
								class="block rounded-lg border border-gray-200 p-3 hover:border-purple-300 hover:bg-purple-50 transition-colors"
							>
								<p class="font-medium text-gray-900 text-sm leading-snug">
									{member.title ?? 'Untitled'}
								</p>
								<div class="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
									{#if member.author}
										<span>{member.author}</span>
									{/if}
									{#if getSource(member.url)}
										<span>{getSource(member.url)}</span>
									{/if}
									{#if member.published_at}
										<span>{formatDate(member.published_at)}</span>
									{/if}
									<span class="rounded bg-gray-100 px-1 font-medium text-gray-600">
										{member.importance_score}/10
									</span>
								</div>
							</a>
						</li>
					{/each}
				</ul>
			</section>
		</article>
	{/if}
</main>
