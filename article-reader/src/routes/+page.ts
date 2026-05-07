import type { PageLoad } from './$types';
import { getAllArticles } from '$lib/api';
import { extractCategories, buildDateFrom } from '$lib/utils';
import { get } from 'svelte/store';
import { settings } from '$lib/stores/settings';
import type { CategoryCount } from '$lib/types';

export const load: PageLoad = async ({ depends }) => {
	depends('app:home');
	const s = get(settings);
	try {
		const articles = await getAllArticles({
			min_score: s.minScore,
			date_from: buildDateFrom(s.daysBack)
		});
		return { categories: extractCategories(articles), error: null };
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load articles';
		return { categories: [] as CategoryCount[], error };
	}
};
