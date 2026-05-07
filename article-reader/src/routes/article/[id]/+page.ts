import type { PageLoad } from './$types';
import { getArticleDetail } from '$lib/api';
import type { ArticleDetail } from '$lib/types';

export const load: PageLoad = async ({ params }) => {
	const id = parseInt(params.id, 10);
	if (isNaN(id)) {
		return { article: null as ArticleDetail | null, error: 'Invalid article ID' };
	}
	try {
		const article = await getArticleDetail(id);
		return { article, error: null };
	} catch (e) {
		const error = e instanceof Error ? e.message : 'Failed to load article';
		return { article: null as ArticleDetail | null, error };
	}
};
