import type { ArticleSummary, CategoryCount } from './types';

export function extractCategories(articles: ArticleSummary[]): CategoryCount[] {
	const counts = new Map<string, number>();
	for (const article of articles) {
		for (const tag of article.tags) {
			counts.set(tag.category, (counts.get(tag.category) ?? 0) + 1);
		}
	}
	return Array.from(counts.entries()).map(([category, count]) => ({ category, count }));
}

export function buildDateFrom(daysBack: number): string {
	const date = new Date();
	date.setDate(date.getDate() - daysBack);
	return date.toISOString().split('T')[0];
}

export function extractSubcategories(articles: ArticleSummary[], category: string): string[] {
	const seen = new Set<string>();
	for (const article of articles) {
		for (const tag of article.tags) {
			if (tag.category === category && tag.subcategory) {
				seen.add(tag.subcategory);
			}
		}
	}
	return Array.from(seen);
}
