import { describe, expect, it } from 'vitest';
import type { MatchEvent } from './api.js';
import { euros, hidden, merge } from './live.js';

function event(
	seq: number,
	type: string,
	data = {},
	visible_to: string[] | null = null
): MatchEvent {
	return { seq, source: 'game', type, data, visible_to };
}

describe('merge', () => {
	it('keeps every position once and in order, also when a reconnect sends events again', () => {
		const first = [event(0, 'a'), event(1, 'b')];
		const again = [event(1, 'b-again'), event(2, 'c'), event(0, 'a-again')];

		const log = merge(first, again);

		expect(log.map((e) => [e.seq, e.type])).toEqual([
			[0, 'a'],
			[1, 'b'],
			[2, 'c']
		]);
	});
});

describe('hidden', () => {
	it('hides hands, hole cards, roles and win chances only with spoilers off', () => {
		for (const field of ['hand', 'cards', 'role', 'win_probability']) {
			expect(hidden(field, false)).toBe(true);
			expect(hidden(field, true)).toBe(false);
		}
		expect(hidden('stack', false)).toBe(false);
	});
});

describe('euros', () => {
	it('shows millionths of a euro with four decimals, rounded up', () => {
		expect(euros(0)).toBe('0.0000 €');
		expect(euros(350)).toBe('0.0004 €');
		expect(euros(1_234_567)).toBe('1.2346 €');
		expect(euros(1)).toBe('0.0001 €');
		expect(euros(500_000)).toBe('0.5000 €');
	});
});
