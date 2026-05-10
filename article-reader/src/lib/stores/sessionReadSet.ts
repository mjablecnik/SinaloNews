import { writable } from 'svelte/store';

export function createSessionReadSetStore() {
	const { subscribe, update, set } = writable<Set<string>>(new Set());

	return {
		subscribe,
		add(type: 'article' | 'group', id: number) {
			update((s) => new Set(s).add(`${type}:${id}`));
		},
		clear() {
			set(new Set());
		},
		has(type: 'article' | 'group', id: number): boolean {
			let result = false;
			const unsub = subscribe((s) => {
				result = s.has(`${type}:${id}`);
			});
			unsub();
			return result;
		}
	};
}

export const sessionReadSet = createSessionReadSetStore();
