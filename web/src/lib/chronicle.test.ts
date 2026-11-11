import { describe, expect, it } from 'vitest';
import { chroniclePath, explain, isLang, isStyle } from './chronicle.js';

describe('chroniclePath', () => {
	it('builds the address with style, language and format', () => {
		expect(chroniclePath('abc', 'sports', 'de')).toBe(
			'/replays/abc/chronicle?style=sports&lang=de&format=json'
		);
		expect(chroniclePath('a b', 'epic', 'en', 'markdown')).toBe(
			'/replays/a%20b/chronicle?style=epic&lang=en&format=markdown'
		);
	});
});

describe('isStyle and isLang', () => {
	it('know the four styles and two languages', () => {
		for (const style of ['epic', 'news', 'sports', 'novel']) expect(isStyle(style)).toBe(true);
		expect(isStyle('tabloid')).toBe(false);
		expect(isLang('de')).toBe(true);
		expect(isLang('fr')).toBe(false);
		expect(isLang(null)).toBe(false);
	});
});

describe('explain', () => {
	it('says why a match that is running has no chronicle yet', () => {
		expect(explain(409)).toContain('not over yet');
	});

	it('has words for a game without one, an unreachable arena and anything else', () => {
		expect(explain(404)).toContain('no chronicle');
		expect(explain(502)).toContain('did not answer');
		expect(explain(500)).toContain('(500)');
	});
});
