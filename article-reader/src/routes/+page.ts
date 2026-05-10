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
		const articleIdsByCategory: Record<string, number[]> = {};
		for (const article of articles) {
			for (const tag of article.tags) {
				if (!articleIdsByCategory[tag.category]) articleIdsByCategory[tag.category] = [];
				articleIdsByCategory[tag.category].push(article.id);
			}
		}
		const allArticleIds = articles.map((a) => a.id);
		return {
			categories: extractCategories(articles),
			totalCount: articles.length,
			articleIdsByCategory,
			allArticleIds,
			error: null
		};
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load articles';
		return {
			categories: [] as CategoryCount[],
			totalCount: 0,
			articleIdsByCategory: {} as Record<string, number[]>,
			allArticleIds: [] as number[],
			error
		};
	}
};
