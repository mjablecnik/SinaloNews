import { writable } from 'svelte/store';
import { readState } from './readState';

const STORAGE_KEY = 'article-reader:read-groups';

function loadGroupIds(): number[] {
	if (typeof localStorage === 'undefined') return [];
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return [];
		const parsed = JSON.parse(raw);
		if (Array.isArray(parsed) && parsed.every((x) => typeof x === 'number')) {
			return parsed;
		}
		console.warn('Invalid group read state in localStorage, resetting');
		return [];
	} catch {
		console.warn('Failed to load group read state from localStorage, resetting');
		return [];
	}
}

export function createGroupReadStateStore() {
	const { subscribe, update } = writable<number[]>(loadGroupIds());

	function persist(ids: number[]) {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
		}
	}

	return {
		subscribe,
		markGroupAsRead(groupId: number, memberArticleIds: number[]) {
			update((ids) => {
				const next = ids.includes(groupId) ? ids : [...ids, groupId];
				persist(next);
				return next;
			});
			for (const articleId of memberArticleIds) {
				readState.markAsRead(articleId);
			}
		},
		isGroupRead(id: number): boolean {
			let result = false;
			const unsub = subscribe((ids) => {
				result = ids.includes(id);
			});
			unsub();
			return result;
		}
	};
}

export const groupReadState = createGroupReadStateStore();
