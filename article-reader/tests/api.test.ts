import { describe, it, vi, beforeEach, afterEach } from 'vitest';
import fc from 'fast-check';

vi.mock('$env/static/public', () => ({
	PUBLIC_ARTICLE_API_URL: 'http://localhost:8002'
}));

import { buildUrl, getAllArticles } from '../src/lib/api';
import type { ArticleSummary } from '../src/lib/types';

const BASE_URL = 'http://localhost:8002';

function makeMockArticle(id: number): ArticleSummary {
	return {
		id,
		title: `Article ${id}`,
		url: null,
		author: null,
		published_at: null,
		tags: [],
		content_type: 'article',
		importance_score: 7,
		summary: null,
		classified_at: '2024-01-01T00:00:00Z'
	};
}

describe('buildUrl', () => {
	it('all non-undefined params appear in the URL', () => {
		fc.assert(
			fc.property(
				fc.record({
					category: fc.option(fc.hexaString({ minLength: 1, maxLength: 20 }), {
						nil: undefined
					}),
					subcategory: fc.option(fc.hexaString({ minLength: 1, maxLength: 20 }), {
						nil: undefined
					}),
					min_score: fc.option(fc.integer({ min: 0, max: 10 }), { nil: undefined }),
					page: fc.option(fc.integer({ min: 1, max: 100 }), { nil: undefined })
				}),
				(params) => {
					const url = buildUrl('/api/articles', params);
					const urlObj = new URL(url);
					for (const [key, value] of Object.entries(params)) {
						if (value !== undefined) {
							if (urlObj.searchParams.get(key) !== String(value)) return false;
						}
					}
					return true;
				}
			)
		);
	});

	it('undefined params are not included in URL', () => {
		fc.assert(
			fc.property(
				fc.record({
					category: fc.option(fc.hexaString({ minLength: 1, maxLength: 20 }), {
						nil: undefined
					}),
					subcategory: fc.option(fc.hexaString({ minLength: 1, maxLength: 20 }), {
						nil: undefined
					})
				}),
				(params) => {
					const url = buildUrl('/api/articles', params);
					const urlObj = new URL(url);
					for (const [key, value] of Object.entries(params)) {
						if (value === undefined && urlObj.searchParams.has(key)) return false;
					}
					return true;
				}
			)
		);
	});

	it('URL starts with the base URL', () => {
		fc.assert(
			fc.property(
				fc.record({
					path: fc.constantFrom('/api/articles', '/api/articles/1'),
					params: fc.record({ page: fc.option(fc.integer({ min: 1 }), { nil: undefined }) })
				}),
				({ path, params }) => {
					const url = buildUrl(path, params);
					return url.startsWith(BASE_URL);
				}
			)
		);
	});
});

describe('getAllArticles pagination', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
	});

	it('collects all items across multiple pages', async () => {
		await fc.assert(
			fc.asyncProperty(
				fc.integer({ min: 0, max: 300 }),
				async (total) => {
					const pageSize = 100;
					const totalPages = total === 0 ? 1 : Math.ceil(total / pageSize);
					const allItems = Array.from({ length: total }, (_, i) => makeMockArticle(i + 1));

					(fetch as ReturnType<typeof vi.fn>).mockImplementation(async (url: string) => {
						const urlObj = new URL(url as string);
						const page = parseInt(urlObj.searchParams.get('page') || '1');
						const size = parseInt(urlObj.searchParams.get('size') || '100');
						const start = (page - 1) * size;
						const items = allItems.slice(start, start + size);
						return {
							ok: true,
							json: async () => ({ items, total, page, size, pages: totalPages })
						};
					});

					const result = await getAllArticles({});
					return result.length === total;
				}
			)
		);
	});

	it('pages needed equals Math.ceil(total / pageSize)', async () => {
		await fc.assert(
			fc.asyncProperty(
				fc.integer({ min: 1, max: 500 }),
				async (total) => {
					const pageSize = 100;
					const expectedPages = Math.ceil(total / pageSize);
					const allItems = Array.from({ length: total }, (_, i) => makeMockArticle(i + 1));
					let fetchCallCount = 0;

					(fetch as ReturnType<typeof vi.fn>).mockImplementation(async (url: string) => {
						fetchCallCount++;
						const urlObj = new URL(url as string);
						const page = parseInt(urlObj.searchParams.get('page') || '1');
						const size = parseInt(urlObj.searchParams.get('size') || '100');
						const start = (page - 1) * size;
						const items = allItems.slice(start, start + size);
						return {
							ok: true,
							json: async () => ({ items, total, page, size, pages: expectedPages })
						};
					});

					fetchCallCount = 0;
					await getAllArticles({});
					return fetchCallCount === expectedPages;
				}
			)
		);
	});
});
