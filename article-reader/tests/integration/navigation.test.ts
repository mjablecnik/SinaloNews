import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';

vi.mock('$app/navigation', () => ({
	goto: vi.fn(),
	invalidate: vi.fn(),
	beforeNavigate: vi.fn()
}));

vi.mock('$app/stores', () => ({
	navigating: { subscribe: vi.fn((fn: (v: null) => void) => { fn(null); return () => {}; }) },
	page: { subscribe: vi.fn((fn: (v: object) => void) => { fn({}); return () => {}; }) },
	updated: { subscribe: vi.fn((fn: (v: boolean) => void) => { fn(false); return () => {}; }) }
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_ARTICLE_API_URL: 'http://localhost:8002'
}));

import { goto, invalidate } from '$app/navigation';
import CategoryPage from '../../src/routes/+page.svelte';
import ArticleListPage from '../../src/routes/category/[slug]/+page.svelte';
import ArticleDetailPage from '../../src/routes/article/[id]/+page.svelte';
import SettingsPage from '../../src/routes/settings/+page.svelte';
import type { ArticleSummary, ArticleDetail, FeedItem } from '../../src/lib/types';

function mockArticle(overrides: Partial<ArticleSummary> = {}): ArticleSummary {
	return {
		id: 1,
		title: 'Test Article',
		url: 'https://example.com/article',
		author: 'Test Author',
		published_at: '2024-06-01T00:00:00Z',
		tags: [{ category: 'Technology', subcategory: 'AI' }],
		content_type: 'article',
		importance_score: 8,
		summary: 'This is a test article summary.',
		classified_at: '2024-06-01T12:00:00Z',
		...overrides
	};
}

function mockFeedItem(overrides: Partial<FeedItem> = {}): FeedItem {
	return {
		type: 'article',
		id: 1,
		title: 'Test Article',
		url: 'https://example.com/article',
		author: 'Test Author',
		published_at: '2024-06-01T00:00:00Z',
		tags: [{ category: 'Technology', subcategory: 'AI' }],
		content_type: 'article',
		importance_score: 8,
		summary: 'This is a test article summary.',
		classified_at: '2024-06-01T12:00:00Z',
		category: 'Technology',
		...overrides
	};
}

function mockArticleDetail(overrides: Partial<ArticleDetail> = {}): ArticleDetail {
	return {
		...mockArticle(),
		extracted_text: 'Full article text goes here.',
		...overrides
	};
}

beforeEach(() => {
	vi.clearAllMocks();
	localStorage.clear();
});

// Task 10.1: Navigation flow tests
describe('navigation flow', () => {
	it('Category Selection: clicking a category card navigates to article list', async () => {
		render(CategoryPage, {
			data: {
				categories: [
					{ category: 'Technology', count: 5 },
					{ category: 'Politics', count: 2 }
				],
				totalCount: 7,
				articleIdsByCategory: { Technology: [1, 2], Politics: [3] },
				allArticleIds: [1, 2, 3],
				error: null
			}
		});

		const techCard = screen.getByText('Technology');
		await fireEvent.click(techCard);

		expect(goto).toHaveBeenCalledWith('/category/Technology');
	});

	it('Article List: clicking an article card navigates to article detail', async () => {
		const article = mockFeedItem({ id: 42, summary: 'Summary of article 42.' });

		render(ArticleListPage, {
			data: { category: 'Technology', items: [article], error: null }
		});

		const summaryEl = screen.getByText('Summary of article 42.');
		await fireEvent.click(summaryEl);

		expect(goto).toHaveBeenCalledWith('/article/42');
	});

	it('Settings page: saving settings navigates back to home', async () => {
		render(SettingsPage, {});

		const form = document.querySelector('form')!;
		await fireEvent.submit(form);

		expect(goto).toHaveBeenCalledWith('/');
	});

	it('Article list: settings link points to /settings', () => {
		render(ArticleListPage, {
			data: { category: 'Technology', items: [mockFeedItem()], error: null }
		});

		const settingsLink = screen.getByTitle('Settings');
		expect(settingsLink.getAttribute('href')).toBe('/settings');
	});

	it('Article detail: back button calls history.back', async () => {
		const backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => {});

		render(ArticleDetailPage, {
			data: { article: mockArticleDetail(), error: null }
		});

		const backBtn = screen.getByText('← Back');
		await fireEvent.click(backBtn);

		expect(backSpy).toHaveBeenCalled();
		backSpy.mockRestore();
	});
});

// Task 10.2: Error handling tests
describe('error handling', () => {
	it('API unreachable on category screen shows error message', () => {
		render(CategoryPage, {
			data: { categories: [], totalCount: 0, articleIdsByCategory: {}, allArticleIds: [], error: 'Service unavailable' }
		});

		expect(screen.getByText('Service unavailable')).toBeTruthy();
	});

	it('Category screen error: Try Again button calls invalidate', async () => {
		render(CategoryPage, {
			data: { categories: [], totalCount: 0, articleIdsByCategory: {}, allArticleIds: [], error: 'Service unavailable' }
		});

		const retryBtn = screen.getByText('Try Again');
		await fireEvent.click(retryBtn);

		expect(invalidate).toHaveBeenCalledWith('app:home');
	});

	it('Article detail 404: shows error message and back navigation', () => {
		render(ArticleDetailPage, {
			data: { article: null, error: 'Article not found' }
		});

		expect(screen.getByText('Article not found')).toBeTruthy();
		expect(screen.getByText('← Back')).toBeTruthy();
	});

	it('Article list API error shows error message', () => {
		render(ArticleListPage, {
			data: { category: 'Technology', items: [], error: 'Failed to load articles' }
		});

		expect(screen.getByText('Failed to load articles')).toBeTruthy();
	});

	it('Article list: reload button calls invalidate and not a classification endpoint', async () => {
		render(ArticleListPage, {
			data: { category: 'Technology', items: [mockFeedItem()], error: null }
		});

		const reloadBtn = screen.getByText('↻ Reload');
		await fireEvent.click(reloadBtn);

		expect(invalidate).toHaveBeenCalledWith('app:category');
		// Ensure no classification-triggering call was made
		const calls = (invalidate as ReturnType<typeof vi.fn>).mock.calls;
		const hasClassifCall = calls.some(
			([arg]: [string]) => typeof arg === 'string' && arg.includes('classif')
		);
		expect(hasClassifCall).toBe(false);
	});
});
