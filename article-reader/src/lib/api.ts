import { PUBLIC_ARTICLE_API_URL } from '$env/static/public';
import type { ArticleDetail, ArticleSummary, PaginatedResponse } from './types';

export interface ArticleQueryParams {
	category?: string;
	subcategory?: string;
	min_score?: number;
	date_from?: string;
	sort_by?: string;
	sort_order?: string;
	page?: number;
	size?: number;
}

function buildUrl(path: string, params: Record<string, string | number | undefined>): string {
	const url = new URL(`${PUBLIC_ARTICLE_API_URL}${path}`);
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined && value !== null) {
			url.searchParams.set(key, String(value));
		}
	}
	return url.toString();
}

export async function getArticles(params: ArticleQueryParams): Promise<PaginatedResponse> {
	const url = buildUrl('/api/articles', params as Record<string, string | number | undefined>);
	const response = await fetch(url);
	if (!response.ok) {
		throw new Error(`Failed to fetch articles: ${response.status} ${response.statusText}`);
	}
	return response.json() as Promise<PaginatedResponse>;
}

export async function getArticleDetail(id: number): Promise<ArticleDetail> {
	const url = `${PUBLIC_ARTICLE_API_URL}/api/articles/${id}`;
	const response = await fetch(url);
	if (!response.ok) {
		if (response.status === 404) {
			throw new Error('Article not found');
		}
		throw new Error(`Failed to fetch article: ${response.status} ${response.statusText}`);
	}
	return response.json() as Promise<ArticleDetail>;
}

export async function getAllArticles(params: ArticleQueryParams): Promise<ArticleSummary[]> {
	const pageSize = 100;
	const firstPage = await getArticles({ ...params, page: 1, size: pageSize });
	const allItems: ArticleSummary[] = [...firstPage.items];

	const totalPages = firstPage.pages;
	if (totalPages > 1) {
		const pagePromises: Promise<PaginatedResponse>[] = [];
		for (let page = 2; page <= totalPages; page++) {
			pagePromises.push(getArticles({ ...params, page, size: pageSize }));
		}
		const pages = await Promise.all(pagePromises);
		for (const page of pages) {
			allItems.push(...page.items);
		}
	}

	return allItems;
}
