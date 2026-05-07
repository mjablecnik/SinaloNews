import type { PageLoad } from './$types';
import { getAllArticles } from '$lib/api';
import { buildDateFrom } from '$lib/utils';
import { get } from 'svelte/store';
import { settings } from '$lib/stores/settings';
import type { ArticleSummary } from '$lib/types';

function sortArticles(articles: ArticleSummary[]): ArticleSummary[] {
	return [...articles].sort((a, b) => {
		const dateA = a.published_at ? new Date(a.published_at).toDateString() : '';
		const dateB = b.published_at ? new Date(b.published_at).toDateString() : '';
		if (dateA !== dateB) {
			const timeA = a.published_at ? new Date(a.published_at).getTime() : 0;
			const timeB = b.published_at ? new Date(b.published_at).getTime() : 0;
			return timeB - timeA; // newest first
		}
		return b.importance_score - a.importance_score;
	});
}

export const load: PageLoad = async ({ params, depends }) => {
	depends('app:category');
	const s = get(settings);
	const category = decodeURIComponent(params.slug);
	try {
		const articles = await getAllArticles({
			category,
			min_score: s.minScore,
			date_from: buildDateFrom(s.daysBack),
			sort_by: 'published_at',
			sort_order: 'desc'
		});
		return { articles: sortArticles(articles), category, error: null };
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load articles';
		return { articles: [] as ArticleSummary[], category, error };
	}
};
