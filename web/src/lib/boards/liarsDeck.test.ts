import { describe, expect, it } from 'vitest';
import type { MatchEvent } from '../api.js';
import { face, sides, tableCardName } from './liarsDeck.js';

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
