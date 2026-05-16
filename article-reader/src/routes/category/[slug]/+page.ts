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
	const isAllInOne = category === '__all__';
	try {
		const pageSize = 30;
		const feedParams = {
			...(isAllInOne ? {} : { category }),
			min_score: s.minScore,
			date_from: buildDateFrom(s.daysBack),
			page: 1,
			size: pageSize
		};
		const firstPage = await getFeed(feedParams);
		return {
			items: firstPage.items,
			category,
			totalPages: firstPage.pages,
			totalCount: firstPage.total,
			currentPage: 1,
			pageSize,
			error: null
		};
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load feed';
		return {
			items: [] as FeedItem[],
			category,
			totalPages: 0,
			totalCount: 0,
			currentPage: 1,
			pageSize: 30,
			error
		};
	}
};
