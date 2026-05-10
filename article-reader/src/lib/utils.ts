import type { ArticleSummary, CategoryCount, FeedItem } from './types';

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

/**
 * Sanitize summary text by removing image URLs, base64 data, and other garbage.
 * Then truncate to maxLength characters.
 */
export function sanitizeSummary(text: string, maxLength = 800): string {
	let clean = text;
	// Remove image URLs (e.g., .gstatic.com/images?q=...)
	clean = clean.replace(/https?:\/\/\S+\.(jpg|jpeg|png|gif|webp|svg|bmp)\S*/gi, '');
	// Remove data URIs and base64 blobs
	clean = clean.replace(/data:[^\s]+/g, '');
	// Remove standalone URLs that look like image queries or long encoded strings (>100 chars)
	clean = clean.replace(/https?:\/\/\S{100,}/g, '');
	// Remove lines that are mostly non-word characters (encoded garbage)
	clean = clean
		.split('\n')
		.filter((line) => {
			const wordChars = line.replace(/[^a-zA-ZÀ-žА-я0-9\s]/g, '').length;
			return line.trim().length === 0 || wordChars > line.trim().length * 0.3;
		})
		.join('\n');
	// Collapse multiple newlines
	clean = clean.replace(/\n{3,}/g, '\n\n').trim();
	// Truncate
	if (clean.length > maxLength) {
		clean = clean.slice(0, maxLength).replace(/\s+\S*$/, '') + '…';
	}
	return clean;
}

/**
 * Format extracted_text into readable markdown paragraphs.
 * Splits on double newlines, and converts single newlines within paragraphs to spaces.
 */
export function formatExtractedText(text: string): string {
	// Split into paragraphs by double newline
	const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim().length > 0);
	// Within each paragraph, collapse single newlines to spaces
	return paragraphs.map((p) => p.replace(/\n/g, ' ').trim()).join('\n\n');
}

export function formatDateTime(dateStr: string | null): string {
	if (!dateStr) return '';
	const date = new Date(dateStr);
	return (
		date.toLocaleDateString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		}) +
		' ' +
		date.toLocaleTimeString(undefined, {
			hour: '2-digit',
			minute: '2-digit'
		})
	);
}

export function formatDateOnly(dateStr: string): string {
	return new Date(dateStr).toISOString().split('T')[0];
}

export function extractUniqueDates(items: FeedItem[]): string[] {
	const dates = new Set<string>();
	for (const item of items) {
		const dateStr = item.published_at ?? item.grouped_date;
		if (dateStr) {
			dates.add(formatDateOnly(dateStr));
		}
	}
	return Array.from(dates).sort().reverse();
}

export function getTodayDateString(): string {
	return new Date().toISOString().split('T')[0];
}

export function sortByDateThenImportance(items: FeedItem[]): FeedItem[] {
	return [...items].sort((a, b) => {
		const dateA = a.published_at ?? a.grouped_date ?? '';
		const dateB = b.published_at ?? b.grouped_date ?? '';
		const dateCmp = dateB.localeCompare(dateA);
		if (dateCmp !== 0) return dateCmp;
		return b.importance_score - a.importance_score;
	});
}

export function filterReadItems(
	items: FeedItem[],
	readArticleIds: number[],
	readGroupIds: number[],
	sessionReadSet: Set<string>
): FeedItem[] {
	return items.filter((item) => {
		const key = `${item.type}:${item.id}`;
		if (sessionReadSet.has(key)) return true;
		if (item.type === 'article' && readArticleIds.includes(item.id)) return false;
		if (item.type === 'group' && readGroupIds.includes(item.id)) return false;
		return true;
	});
}
