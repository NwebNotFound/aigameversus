import { describe, expect, it } from 'vitest';
import { card, coins, percent, positionTag, seatPoint } from './pokerTable.js';

describe('seatPoint', () => {
	it('puts the first seat at the bottom and spreads the rest around the oval', () => {
		expect(seatPoint(0, 4)).toEqual({ left: 50, top: 87 });
		expect(seatPoint(1, 4).left).toBeLessThan(15);
		expect(seatPoint(2, 4).top).toBeLessThan(15);
		expect(seatPoint(3, 4).left).toBeGreaterThan(85);
	});

	it('keeps every seat of a six-handed table inside the box and apart', () => {
		const points = Array.from({ length: 6 }, (_, i) => seatPoint(i, 6));
		for (const p of points) {
			expect(p.left).toBeGreaterThanOrEqual(0);
			expect(p.left).toBeLessThanOrEqual(100);
			expect(p.top).toBeGreaterThanOrEqual(0);
			expect(p.top).toBeLessThanOrEqual(100);
		}
		expect(new Set(points.map((p) => `${p.left}/${p.top}`)).size).toBe(6);
	});
});

describe('card', () => {
	it('reads rank and suit', () => {
		expect(card('Ah')).toEqual({ rank: 'A', symbol: '♥', red: true, label: 'A of hearts' });
		expect(card('Td')).toMatchObject({ rank: '10', symbol: '♦', red: true });
		expect(card('2c')).toMatchObject({ symbol: '♣', red: false });
	});

	it('refuses what is not a card', () => {
		expect(card('')).toBeNull();
		expect(card('1h')).toBeNull();
		expect(card('Ax')).toBeNull();
		expect(card('Ahh')).toBeNull();
	});
});

describe('coins', () => {
	it('draws bigger stacks with more coins, from none to five', () => {
		expect(coins(0)).toBe(0);
		expect(coins(10)).toBe(1);
		expect(coins(1000)).toBe(3);
		expect(coins(1_000_000)).toBe(5);
	});
});

describe('percent and positionTag', () => {
	it('rounds a chance and says "–" without one', () => {
		expect(percent(0.756)).toBe('76%');
		expect(percent(0)).toBe('0%');
		expect(percent(null)).toBe('–');
	});

	it('tags the button and the blinds only', () => {
		expect(positionTag('button')).toBe('D');
		expect(positionTag('big_blind')).toBe('BB');
		expect(positionTag('seat_3')).toBeNull();
		expect(positionTag(null)).toBeNull();
	});
});
