import { describe, it, expect, beforeEach } from 'vitest';
import fc from 'fast-check';
import { createReadStateStore } from '../src/lib/stores/readState';

describe('readState store', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it('isRead returns true iff ID was marked as read', () => {
		fc.assert(
			fc.property(
				fc.array(fc.integer({ min: 1, max: 10000 }), { maxLength: 50 }),
				fc.integer({ min: 1, max: 10000 }),
				(readIds, queryId) => {
					localStorage.clear();
					const store = createReadStateStore();
					for (const id of readIds) {
						store.markAsRead(id);
					}
					return store.isRead(queryId) === readIds.includes(queryId);
				}
			)
		);
	});

	it('markAsRead adds ID (round-trip: mark then isRead returns true)', () => {
		fc.assert(
			fc.property(fc.integer({ min: 1, max: 10000 }), (id) => {
				localStorage.clear();
				const store = createReadStateStore();
				store.markAsRead(id);
				return store.isRead(id) === true;
			})
		);
	});

	it('unknown IDs return false from isRead by default', () => {
		fc.assert(
			fc.property(fc.integer({ min: 1, max: 10000 }), (id) => {
				localStorage.clear();
				const store = createReadStateStore();
				return store.isRead(id) === false;
			})
		);
	});

	it('markAsRead is idempotent (no duplicate IDs stored)', () => {
		fc.assert(
			fc.property(fc.integer({ min: 1, max: 10000 }), (id) => {
				localStorage.clear();
				const store = createReadStateStore();
				store.markAsRead(id);
				store.markAsRead(id);

				let count = 0;
				const unsub = store.subscribe((ids) => {
					count = ids.filter((x) => x === id).length;
				});
				unsub();
				return count === 1;
			})
		);
	});

	it('isRead reflects persisted state across store instances', () => {
		fc.assert(
			fc.property(fc.integer({ min: 1, max: 10000 }), (id) => {
				localStorage.clear();
				const store1 = createReadStateStore();
				store1.markAsRead(id);

				const store2 = createReadStateStore();
				return store2.isRead(id) === true;
			})
		);
	});
});
