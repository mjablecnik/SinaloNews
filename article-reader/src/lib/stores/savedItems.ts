import { writable } from 'svelte/store';
import type { SavedItems } from '../types';

const STORAGE_KEY = 'article-reader:saved-items';

const DEFAULT: SavedItems = { articles: [], groups: [] };

function isValidSavedItems(value: unknown): value is SavedItems {
	if (typeof value !== 'object' || value === null) return false;
	const v = value as Record<string, unknown>;
	return (
		Array.isArray(v.articles) &&
		v.articles.every((x) => typeof x === 'number') &&
		Array.isArray(v.groups) &&
		v.groups.every((x) => typeof x === 'number')
	);
}

function loadSavedItems(): SavedItems {
	if (typeof localStorage === 'undefined') return { ...DEFAULT, articles: [], groups: [] };
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return { articles: [], groups: [] };
		const parsed = JSON.parse(raw);
		if (isValidSavedItems(parsed)) return parsed;
		console.warn('Invalid saved items in localStorage, resetting');
		return { articles: [], groups: [] };
	} catch {
		console.warn('Failed to load saved items from localStorage, resetting');
		return { articles: [], groups: [] };
	}
}

export function createSavedItemsStore() {
	const { subscribe, update } = writable<SavedItems>(loadSavedItems());

	function persist(value: SavedItems) {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
		}
	}

	return {
		subscribe,
		toggleArticle(id: number) {
			update((state) => {
				const articles = state.articles.includes(id)
					? state.articles.filter((x) => x !== id)
					: [...state.articles, id];
				const next = { ...state, articles };
				persist(next);
				return next;
			});
		},
		toggleGroup(id: number) {
			update((state) => {
				const groups = state.groups.includes(id)
					? state.groups.filter((x) => x !== id)
					: [...state.groups, id];
				const next = { ...state, groups };
				persist(next);
				return next;
			});
		},
		removeArticle(id: number) {
			update((state) => {
				const next = { ...state, articles: state.articles.filter((x) => x !== id) };
				persist(next);
				return next;
			});
		},
		removeGroup(id: number) {
			update((state) => {
				const next = { ...state, groups: state.groups.filter((x) => x !== id) };
				persist(next);
				return next;
			});
		},
		isArticleSaved(id: number): boolean {
			let result = false;
			const unsub = subscribe((state) => {
				result = state.articles.includes(id);
			});
			unsub();
			return result;
		},
		isGroupSaved(id: number): boolean {
			let result = false;
			const unsub = subscribe((state) => {
				result = state.groups.includes(id);
			});
			unsub();
			return result;
		}
	};
}

export const savedItems = createSavedItemsStore();
