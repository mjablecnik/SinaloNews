import type { PageLoad } from './$types';
import { get } from 'svelte/store';
import { savedItems } from '$lib/stores/savedItems';
import { getArticleDetail, getGroupDetail } from '$lib/api';
import type { ArticleDetail, GroupDetail } from '$lib/types';

export interface SavedItem {
	type: 'article' | 'group';
	id: number;
	data: ArticleDetail | GroupDetail | null;
}

export const load: PageLoad = async () => {
	const saved = get(savedItems);

	const articleIds = [...saved.articles].reverse();
	const groupIds = [...saved.groups].reverse();

	const [articleItems, groupItems] = await Promise.all([
		Promise.all(
			articleIds.map(async (id): Promise<SavedItem> => {
				try {
					const data = await getArticleDetail(id);
					return { type: 'article', id, data };
				} catch {
					return { type: 'article', id, data: null };
				}
			})
		),
		Promise.all(
			groupIds.map(async (id): Promise<SavedItem> => {
				try {
					const data = await getGroupDetail(id);
					return { type: 'group', id, data };
				} catch {
					return { type: 'group', id, data: null };
				}
			})
		)
	]);

	return { items: [...articleItems, ...groupItems] };
};
