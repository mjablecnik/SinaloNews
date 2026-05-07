import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { extractCategories } from '../src/lib/utils';
import type { ArticleSummary } from '../src/lib/types';

const categoryArb = fc.constantFrom('tech', 'sports', 'politics', 'science', 'health');

const tagArb = fc.record({
	category: categoryArb,
	subcategory: fc.hexaString({ minLength: 1, maxLength: 10 })
});

const articleArb: fc.Arbitrary<ArticleSummary> = fc.record({
	id: fc.integer({ min: 1, max: 100000 }),
	title: fc.option(fc.string(), { nil: null }),
	url: fc.option(fc.string(), { nil: null }),
	author: fc.option(fc.string(), { nil: null }),
	published_at: fc.option(fc.string(), { nil: null }),
	tags: fc.array(tagArb, { minLength: 0, maxLength: 5 }),
	content_type: fc.string(),
	importance_score: fc.integer({ min: 0, max: 10 }),
	summary: fc.option(fc.string(), { nil: null }),
	classified_at: fc.string()
});

describe('extractCategories', () => {
	it('sum of counts equals total tag references', () => {
		fc.assert(
			fc.property(fc.array(articleArb, { maxLength: 50 }), (articles) => {
				const categories = extractCategories(articles);
				const totalTags = articles.reduce((sum, a) => sum + a.tags.length, 0);
				const countSum = categories.reduce((sum, c) => sum + c.count, 0);
				return countSum === totalTags;
			})
		);
	});

	it('each count matches number of tags with that category', () => {
		fc.assert(
			fc.property(fc.array(articleArb, { maxLength: 50 }), (articles) => {
				const categories = extractCategories(articles);
				for (const { category, count } of categories) {
					const expected = articles.reduce(
						(sum, a) => sum + a.tags.filter((t) => t.category === category).length,
						0
					);
					if (count !== expected) return false;
				}
				return true;
			})
		);
	});

	it('no duplicate categories in result', () => {
		fc.assert(
			fc.property(fc.array(articleArb, { maxLength: 50 }), (articles) => {
				const categories = extractCategories(articles);
				const names = categories.map((c) => c.category);
				return new Set(names).size === names.length;
			})
		);
	});

	it('empty article list produces empty category list', () => {
		expect(extractCategories([])).toEqual([]);
	});
});
