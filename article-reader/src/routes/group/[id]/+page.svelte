<script lang="ts">
	import type { PageData } from './$types';
	import { onMount } from 'svelte';
	import { groupReadState } from '$lib/stores/groupReadState';
	import { savedItems } from '$lib/stores/savedItems';
	import { formatDateTime } from '$lib/utils';
	import MarkdownRenderer from '$lib/components/MarkdownRenderer.svelte';
	import ErrorMessage from '$lib/components/ErrorMessage.svelte';
	import SaveButton from '$lib/components/SaveButton.svelte';

	let { data }: { data: PageData } = $props();

	onMount(() => {
		if (data.group) {
			groupReadState.markGroupAsRead(
				data.group.id,
				data.group.members.map((m) => m.id)
			);
		}
	});

	function getSource(url: string | null): string {
		if (!url) return '';
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return '';
		}
	}

	// Accordion state for source summaries
	let expandedSources = $state(new Set<number>());

	function toggleSummary(index: number) {
		const next = new Set(expandedSources);
		if (next.has(index)) {
			next.delete(index);
		} else {
			next.add(index);
		}
		expandedSources = next;
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
			<div class="mb-4 space-y-2">
				<div class="flex items-center gap-2">
					<span class="rounded bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-700">
						Group · {group.member_count} articles
					</span>
					<span class="text-sm text-gray-500">{formatDateTime(group.grouped_date)}</span>
				</div>
				<h1 class="text-xl font-bold text-gray-900">{group.title}</h1>
				<SaveButton
					isSaved={$savedItems.groups.includes(group.id)}
					onToggle={() => savedItems.toggleGroup(group.id)}
				/>
			</div>

			<section class="mb-6">
				<h2 class="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Summary</h2>
				<div class="rounded-lg bg-gray-50 p-4">
					<MarkdownRenderer content={group.summary} />
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
					{#each group.members as member, i}
						<li class="rounded-lg border border-gray-200 overflow-hidden">
							<div class="flex items-center gap-2 p-3">
								<a
									href="/article/{member.id}"
									class="flex-1 min-w-0"
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
											<span>{formatDateTime(member.published_at)}</span>
										{/if}
										<span class="rounded bg-gray-100 px-1 font-medium text-gray-600">
											{member.importance_score}/10
										</span>
									</div>
								</a>
								{#if member.summary}
									<button
										onclick={() => toggleSummary(i)}
										class="shrink-0 rounded p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
										title={expandedSources.has(i) ? 'Hide summary' : 'Show summary'}
									>
										<svg
											xmlns="http://www.w3.org/2000/svg"
											class="h-4 w-4 transition-transform {expandedSources.has(i) ? 'rotate-180' : ''}"
											fill="none"
											viewBox="0 0 24 24"
											stroke="currentColor"
											stroke-width="2"
										>
											<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
										</svg>
									</button>
								{/if}
							</div>
							{#if member.summary && expandedSources.has(i)}
								<div class="border-t border-gray-100 bg-gray-50 px-3 py-2">
									<MarkdownRenderer content={member.summary} />
								</div>
							{/if}
						</li>
					{/each}
				</ul>
			</section>
		</article>
	{/if}
</main>
