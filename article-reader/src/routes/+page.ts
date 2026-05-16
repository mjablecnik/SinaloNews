import type { PageLoad } from './$types';
import { getCategories } from '$lib/api';
import { buildDateFrom } from '$lib/utils';
import { get } from 'svelte/store';
import { settings } from '$lib/stores/settings';
import type { CategoryCount } from '$lib/types';

export const load: PageLoad = async ({ depends }) => {
	depends('app:home');
	const s = get(settings);
	try {
		const data = await getCategories({
			min_score: s.minScore,
			date_from: buildDateFrom(s.daysBack)
		});
		const categories: CategoryCount[] = data.categories.map((c) => ({
			category: c.category,
			count: c.count
		}));
		return {
			categories,
			totalCount: data.total,
			error: null
		};
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load articles';
		return {
			categories: [] as CategoryCount[],
			totalCount: 0,
			error
		};
	}
};
