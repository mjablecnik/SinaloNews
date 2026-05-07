import type { PageLoad } from './$types';
import { getAllArticles } from '$lib/api';
import { buildDateFrom } from '$lib/utils';
import { get } from 'svelte/store';
import { settings } from '$lib/stores/settings';
import type { ArticleSummary } from '$lib/types';

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
			sort_order: 'asc'
		});
		return { articles, category, error: null };
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load articles';
		return { articles: [] as ArticleSummary[], category, error };
	}
};
