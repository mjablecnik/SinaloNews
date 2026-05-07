import { describe, it } from 'vitest';
import fc from 'fast-check';
import { marked } from 'marked';

// Alphanumeric text that won't accidentally contain markdown syntax
const safeTextArb = fc.stringOf(
	fc.mapToConstant(
		{ num: 26, build: (i) => String.fromCharCode(97 + i) }, // a-z
		{ num: 26, build: (i) => String.fromCharCode(65 + i) }, // A-Z
		{ num: 10, build: (i) => String.fromCharCode(48 + i) } // 0-9
	),
	{ minLength: 1, maxLength: 30 }
);

describe('Markdown rendering', () => {
	it('bold syntax produces <strong> in HTML output', () => {
		fc.assert(
			fc.property(safeTextArb, (text) => {
				const md = `**${text}**`;
				const html = marked(md) as string;
				return html.includes('<strong>') && html.includes('</strong>');
			})
		);
	});

	it('italic syntax produces <em> in HTML output', () => {
		fc.assert(
			fc.property(safeTextArb, (text) => {
				const md = `_${text}_`;
				const html = marked(md) as string;
				return html.includes('<em>') && html.includes('</em>');
			})
		);
	});

	it('bullet list syntax produces <li> in HTML output', () => {
		fc.assert(
			fc.property(safeTextArb, (text) => {
				const md = `- ${text}`;
				const html = marked(md) as string;
				return html.includes('<li>') && html.includes('</li>');
			})
		);
	});

	it('combined bold and italic produce both <strong> and <em>', () => {
		fc.assert(
			fc.property(safeTextArb, safeTextArb, (boldText, italicText) => {
				const md = `**${boldText}** and _${italicText}_`;
				const html = marked(md) as string;
				return (
					html.includes('<strong>') &&
					html.includes('</strong>') &&
					html.includes('<em>') &&
					html.includes('</em>')
				);
			})
		);
	});
});
