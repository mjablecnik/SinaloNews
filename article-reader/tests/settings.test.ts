import { describe, it, expect, beforeEach } from 'vitest';
import fc from 'fast-check';
import { createSettingsStore, isValidSettings } from '../src/lib/stores/settings';

describe('settings store', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it('save then load produces identical object', () => {
		fc.assert(
			fc.property(
				fc.record({
					minScore: fc.integer({ min: 0, max: 10 }),
					daysBack: fc.integer({ min: 1, max: 365 })
				}),
				(validSettings) => {
					localStorage.clear();
					const store1 = createSettingsStore();
					store1.set(validSettings);

					const store2 = createSettingsStore();
					let loaded: { minScore: number; daysBack: number } | undefined;
					const unsub = store2.subscribe((v) => {
						loaded = v;
					});
					unsub();

					return (
						loaded !== undefined &&
						loaded.minScore === validSettings.minScore &&
						loaded.daysBack === validSettings.daysBack
					);
				}
			)
		);
	});

	it('rejects minScore outside 0-10', () => {
		fc.assert(
			fc.property(
				fc.oneof(fc.integer({ max: -1 }), fc.integer({ min: 11 })),
				(invalidScore) => {
					return !isValidSettings({ minScore: invalidScore, daysBack: 7 });
				}
			)
		);
	});

	it('rejects daysBack <= 0', () => {
		fc.assert(
			fc.property(fc.integer({ max: 0 }), (invalidDaysBack) => {
				return !isValidSettings({ minScore: 6, daysBack: invalidDaysBack });
			})
		);
	});

	it('accepts valid settings (minScore 0-10, daysBack > 0)', () => {
		fc.assert(
			fc.property(
				fc.record({
					minScore: fc.integer({ min: 0, max: 10 }),
					daysBack: fc.integer({ min: 1, max: 365 })
				}),
				(validSettings) => {
					return isValidSettings(validSettings);
				}
			)
		);
	});

	it('invalid settings are not persisted (store retains previous valid value)', () => {
		localStorage.clear();
		const store = createSettingsStore();
		let currentValue: { minScore: number; daysBack: number } | undefined;
		const unsub = store.subscribe((v) => {
			currentValue = v;
		});

		const initialScore = currentValue!.minScore;
		store.set({ minScore: -5, daysBack: 7 });

		expect(currentValue!.minScore).toBe(initialScore);
		unsub();
	});
});
