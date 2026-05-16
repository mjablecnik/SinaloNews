import type { FeedItem } from '$lib/types';

interface CacheEntry {
	items: FeedItem[];
	currentPage: number;
	totalPages: number;
	totalCount: number;
	selectedDate: string | null;
}

const cache = new Map<string, CacheEntry>();

function buildKey(category: string, date: string | null): string {
	return `${category}::${date ?? '__all__'}`;
}

export function getCachedFeed(category: string, date: string | null): CacheEntry | null {
	const entry = cache.get(buildKey(category, date));
	return entry ?? null;
}

export function setCachedFeed(
	category: string,
	date: string | null,
	entry: CacheEntry
): void {
	cache.set(buildKey(category, date), entry);
}

export function clearFeedCache(category?: string): void {
	if (category === undefined) {
		cache.clear();
	} else {
		for (const key of cache.keys()) {
			if (key.startsWith(`${category}::`)) {
				cache.delete(key);
			}
		}
	}
}
