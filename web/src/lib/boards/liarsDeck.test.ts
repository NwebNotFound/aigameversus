import { describe, expect, it } from 'vitest';
import type { MatchEvent } from '../api.js';
import { face, moments, sides, tableCardName } from './liarsDeck.js';

const event = (seq: number, type: string, data: Record<string, unknown>): MatchEvent => ({
	seq,
	source: 'game',
	type,
	data,
	visible_to: null
});

describe('sides', () => {
	it('seats 2 to 4 players around the table, the first at the bottom', () => {
		expect(sides(2)).toEqual(['bottom', 'top']);
		expect(sides(3)).toEqual(['bottom', 'left', 'right']);
		expect(sides(4)).toEqual(['bottom', 'left', 'top', 'right']);
	});
});

describe('face', () => {
	it('reads rank and number from a card id', () => {
		expect(face('K3')).toMatchObject({ mark: 'K', index: '3', label: 'King 3', joker: false });
		expect(face('A12')).toMatchObject({ mark: 'A', index: '12', label: 'Ace 12' });
	});

	it('knows jokers and the devil card', () => {
		expect(face('J1')).toMatchObject({ mark: '★', joker: true, devil: false });
		expect(face('DV')).toMatchObject({ joker: true, devil: true, label: 'Devil card' });
	});
});

describe('tableCardName', () => {
	it('capitalises the rank and survives a missing one', () => {
		expect(tableCardName('queen')).toBe('Queen');
		expect(tableCardName(null)).toBe('–');
	});
});

describe('moments', () => {
	const log = [
		event(1, 'cards_played', { player: 'p1', count: 1 }),
		event(2, 'liar_called', { caller: 'p2', target: 'p1', automatic: false }),
		event(3, 'trigger_pulled', { player: 'p1', pull: 1, live: false }),
		event(4, 'liar_called', { caller: 'p3', target: 'p2', automatic: true }),
		event(5, 'trigger_pulled', { player: 'p2', pull: 2, live: true })
	];

	it('finds the calls and the shots, oldest first', () => {
		expect(moments(log, 0).map((m) => [m.seq, m.kind, m.text])).toEqual([
			[2, 'liar', 'p2 calls: Liar!'],
			[3, 'shot', 'p1: click'],
			[4, 'liar', 'p3 forced to call: Liar!'],
			[5, 'shot', 'p2: BANG']
		]);
		expect(moments(log, 0)[3].live).toBe(true);
	});

	it('leaves out what was already shown', () => {
		expect(moments(log, 3).map((m) => m.seq)).toEqual([4, 5]);
		expect(moments(log, 5)).toEqual([]);
	});
});
