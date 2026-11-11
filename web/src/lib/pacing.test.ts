import { describe, expect, it } from 'vitest';
import type { TranscriptLine } from './api.js';
import { FLOOR_MS, dwellMs, lineMs, readingMs, waited } from './pacing.js';

function line(
	kind: TranscriptLine['kind'],
	importance: 1 | 2 | 3,
	text = 'x',
	said?: string
): TranscriptLine {
	return {
		seq: 1,
		kind,
		actor: 'p1',
		text,
		detail: null,
		importance,
		raw: said ? { type: 'message', data: { text: said } } : {}
	};
}

describe('the playout director', () => {
	it('gives words reading time, within bounds', () => {
		expect(readingMs('hi')).toBe(900);
		expect(readingMs('one two three four five six seven eight nine ten eleven twelve')).toBe(1020);
		expect(readingMs('word '.repeat(400))).toBe(6000);
	});

	it('holds a highlight longer than a play, and bookkeeping only briefly', () => {
		expect(lineMs(line('action', 3))).toBeGreaterThan(lineMs(line('action', 2)));
		expect(lineMs(line('info', 1))).toBeLessThan(lineMs(line('action', 2)));
		expect(lineMs(line('speech', 2, 'p1: "…"', 'I doubt it, your history says otherwise.'))).toBe(
			readingMs('I doubt it, your history says otherwise.')
		);
	});

	it('takes the longest line of a moment and scales with the speed', () => {
		const moment = [
			line('action', 2),
			line('speech', 2, 'x', 'a b c d e f g h i j k l m n o p q r s t')
		];
		const one = dwellMs(moment, 1);
		expect(one).toBe(readingMs('a b c d e f g h i j k l m n o p q r s t') + 200);
		expect(dwellMs(moment, 2)).toBeCloseTo(one / 2);
	});

	it('a burst of instant tool calls still gets watchable time per moment', () => {
		// Three instant moves: each moment stays at least the floor, at the fastest speed too.
		for (const speed of [0.5, 1, 2, 4]) {
			expect(dwellMs([line('action', 2)], speed)).toBeGreaterThanOrEqual(FLOOR_MS);
			expect(dwellMs([], speed)).toBeGreaterThanOrEqual(FLOOR_MS);
		}
		expect(dwellMs([line('action', 2)], 1)).toBe(1000);
	});

	it('words a running wait', () => {
		expect(waited(12_400)).toBe('12 s');
		expect(waited(65_000)).toBe('1 min 5 s');
		expect(waited(-5)).toBe('0 s');
	});
});
