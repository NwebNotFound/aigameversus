import { describe, expect, it } from 'vitest';
import { NEUTRAL, identities, identity, shapePath } from './players.js';

const seats = ['p1', 'p2', 'p3', 'p4'];

describe('identity', () => {
	it('gives each seat its slot by seat order, with its own colour, shape and dash', () => {
		const all = Object.values(identities(seats));
		expect(all.map((i) => i.slot)).toEqual([1, 2, 3, 4]);
		expect(new Set(all.map((i) => i.colour)).size).toBe(4);
		expect(new Set(all.map((i) => i.shape)).size).toBe(4);
		expect(new Set(all.map((i) => i.dash)).size).toBe(4);
	});

	it('is the same for the same seat everywhere in a match', () => {
		expect(identity('p3', seats)).toEqual(identity('p3', [...seats]));
	});

	it('is neutral for barbarians, an unknown seat, and tables of more than six', () => {
		expect(identity('neutral', seats)).toBe(NEUTRAL);
		expect(identity('p9', seats)).toBe(NEUTRAL);
		const werewolf = Array.from({ length: 8 }, (_, i) => `p${i + 1}`);
		expect(identity('p1', werewolf).coloured).toBe(false);
	});
});

describe('shapePath', () => {
	it('draws a closed path for every shape', () => {
		for (const shape of [
			'circle',
			'diamond',
			'triangle',
			'square',
			'pentagon',
			'star',
			'cross'
		] as const)
			expect(shapePath(shape, 6)).toMatch(/^M.*Z$/);
	});
});
