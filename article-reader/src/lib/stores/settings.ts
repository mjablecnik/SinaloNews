import { writable } from 'svelte/store';
import type { Settings } from '../types';

const STORAGE_KEY = 'article-reader:settings';

const DEFAULT_SETTINGS: Settings = {
	minScore: 6,
	daysBack: 7
};

function isValidSettings(value: unknown): value is Settings {
	if (typeof value !== 'object' || value === null) return false;
	const s = value as Record<string, unknown>;
	return (
		typeof s.minScore === 'number' &&
		s.minScore >= 0 &&
		s.minScore <= 10 &&
		typeof s.daysBack === 'number' &&
		s.daysBack > 0
	);
}

function loadSettings(): Settings {
	if (typeof localStorage === 'undefined') return { ...DEFAULT_SETTINGS };
	try {
		const raw = localStorage.getItem(STORAGE_KEY);
		if (!raw) return { ...DEFAULT_SETTINGS };
		const parsed = JSON.parse(raw);
		if (isValidSettings(parsed)) return parsed;
		console.warn('Invalid settings in localStorage, resetting to defaults');
		return { ...DEFAULT_SETTINGS };
	} catch {
		console.warn('Failed to load settings from localStorage, resetting to defaults');
		return { ...DEFAULT_SETTINGS };
	}
}

function createSettingsStore() {
	const { subscribe, set, update } = writable<Settings>(loadSettings());

	return {
		subscribe,
		set(value: Settings) {
			if (!isValidSettings(value)) {
				console.warn('Attempted to save invalid settings, ignoring');
				return;
			}
			if (typeof localStorage !== 'undefined') {
				localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
			}
			set(value);
		},
		update(fn: (s: Settings) => Settings) {
			update((current) => {
				const next = fn(current);
				if (!isValidSettings(next)) {
					console.warn('Settings update produced invalid value, ignoring');
					return current;
				}
				if (typeof localStorage !== 'undefined') {
					localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
				}
				return next;
			});
		}
	};
}

export const settings = createSettingsStore();
