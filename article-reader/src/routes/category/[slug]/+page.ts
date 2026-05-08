import type { PageLoad } from './$types';
import { getFeed } from '$lib/api';
import { buildDateFrom } from '$lib/utils';
import { get } from 'svelte/store';
import { settings } from '$lib/stores/settings';
import type { FeedItem } from '$lib/types';

export const load: PageLoad = async ({ params, depends }) => {
	depends('app:category');
	const s = get(settings);
	const category = decodeURIComponent(params.slug);
	try {
		const pageSize = 100;
		const firstPage = await getFeed({
			category,
			min_score: s.minScore,
			date_from: buildDateFrom(s.daysBack),
			page: 1,
			size: pageSize
		});
		const allItems: FeedItem[] = [...firstPage.items];
		const totalPages = firstPage.pages;
		if (totalPages > 1) {
			const pagePromises = [];
			for (let page = 2; page <= totalPages; page++) {
				pagePromises.push(
					getFeed({
						category,
						min_score: s.minScore,
						date_from: buildDateFrom(s.daysBack),
						page,
						size: pageSize
					})
				);
			}
			const pages = await Promise.all(pagePromises);
			for (const page of pages) {
				allItems.push(...page.items);
			}
		}
		return { items: allItems, category, error: null };
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load feed';
		return { items: [] as FeedItem[], category, error };
	}
};
