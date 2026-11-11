import { describe, expect, it } from 'vitest';
import type { MatchEvent } from '../api.js';
import { circlePoint, currentVotes, isWolf, roleName, tally, themeOf } from './werewolfCircle.js';

const event = (seq: number, type: string, data: Record<string, unknown> = {}): MatchEvent => ({
	seq,
	source: 'game',
	type,
	data,
	visible_to: null
});

describe('circlePoint', () => {
	it('puts the first seat at the top and goes clockwise', () => {
		expect(circlePoint(0, 4)).toEqual({ left: 50, top: 12 });
		expect(circlePoint(1, 4)).toEqual({ left: 88, top: 50 });
		expect(circlePoint(2, 4)).toEqual({ left: 50, top: 88 });
		expect(circlePoint(3, 4)).toEqual({ left: 12, top: 50 });
	});

	it('keeps sixteen seats apart and inside the box', () => {
		const points = Array.from({ length: 16 }, (_, i) => circlePoint(i, 16));
		expect(new Set(points.map((p) => `${p.left}/${p.top}`)).size).toBe(16);
		for (const p of points) {
			expect(Math.min(p.left, p.top)).toBeGreaterThanOrEqual(0);
			expect(Math.max(p.left, p.top)).toBeLessThanOrEqual(100);
		}
	});
});

describe('themeOf', () => {
	it('is dark at night, dim at dusk and bright otherwise', () => {
		expect(themeOf('night')).toBe('night');
		expect(themeOf('dusk')).toBe('dusk');
		for (const phase of ['setup', 'morning', 'day', 'over', undefined]) {
			expect(themeOf(phase)).toBe('day');
		}
	});
});

describe('currentVotes', () => {
	it('takes the votes of the day, the last one of each voter', () => {
		const log = [
			event(1, 'night_started', { night: 1 }),
			event(2, 'day_started', { day: 1 }),
			event(3, 'vote_cast', { player: 'p1', target: 'p2' }),
			event(4, 'vote_cast', { player: 'p2', target: 'p1' }),
			event(5, 'vote_cast', { player: 'p1', target: 'p3' })
		];
		expect(currentVotes(log)).toEqual([
			{ from: 'p1', to: 'p3' },
			{ from: 'p2', to: 'p1' }
		]);
	});

	it('drops an abstention, keeps votes after the result, clears them at night', () => {
		const voted = [
			event(1, 'day_started', { day: 1 }),
			event(2, 'vote_cast', { player: 'p1', target: 'p2' }),
			event(3, 'vote_cast', { player: 'p1', target: null }),
			event(4, 'vote_cast', { player: 'p3', target: 'p2' }),
			event(5, 'vote_result', { day: 1, executed: 'p2' })
		];
		expect(currentVotes(voted)).toEqual([{ from: 'p3', to: 'p2' }]);
		expect(currentVotes([...voted, event(6, 'night_started', { night: 2 })])).toEqual([]);
	});
});

describe('tally, roleName and isWolf', () => {
	it('counts votes per target', () => {
		expect(
			tally([
				{ from: 'p1', to: 'p3' },
				{ from: 'p2', to: 'p3' },
				{ from: 'p3', to: 'p1' }
			])
		).toEqual({ p3: 2, p1: 1 });
	});

	it('writes roles as words and knows the pack', () => {
		expect(roleName('bear_tamer')).toBe('Bear tamer');
		expect(roleName(null)).toBe('?');
		expect(isWolf('white_wolf')).toBe(true);
		expect(isWolf('seer')).toBe(false);
	});
});
