import { writable } from 'svelte/store';

const STORAGE_KEY = 'article-reader:read-articles';

function loadReadIds(): number[] {
	if (typeof localStorage === 'undefined') return [];
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return [];
		const parsed = JSON.parse(raw);
		if (Array.isArray(parsed) && parsed.every((x) => typeof x === 'number')) {
			return parsed;
		}
		console.warn('Invalid read state in localStorage, resetting');
		return [];
	} catch {
		console.warn('Failed to load read state from localStorage, resetting');
		return [];
	}
}

function createReadStateStore() {
	const { subscribe, update } = writable<number[]>(loadReadIds());

	function persist(ids: number[]) {
		if (typeof localStorage !== 'undefined') {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
		}
	}

	return {
		subscribe,
		markAsRead(id: number) {
			update((ids) => {
				if (ids.includes(id)) return ids;
				const next = [...ids, id];
				persist(next);
				return next;
			});
		},
		isRead(id: number): boolean {
			let result = false;
			const unsub = subscribe((ids) => {
				result = ids.includes(id);
			});
			unsub();
			return result;
		}
	};
}

export const readState = createReadStateStore();
