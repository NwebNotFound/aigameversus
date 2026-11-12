import { describe, expect, it } from 'vitest';
import type { MatchEvent } from '../api.js';
import {
	causeWords,
	circlePoint,
	currentVotes,
	deathsOf,
	isWolf,
	onStage,
	ranking,
	roleName,
	tally,
	themeOf
} from './werewolfCircle.js';

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

describe('deathsOf', () => {
	it('keeps the announced role and cause of each death, in order', () => {
		const deaths = deathsOf([
			event(0, 'player_died', { player: 'p6', role: 'witch', cause: 'wolves' }),
			event(0, 'player_died', { player: 'p3', role: 'villager', cause: 'executed' })
		]);
		expect(deaths.p6).toEqual({ role: 'witch', cause: 'wolves', order: 1 });
		expect(deaths.p3.order).toBe(2);
		expect(causeWords(deaths.p6.cause)).toBe('killed at night');
	});
});

describe('onStage', () => {
	const line = (kind: string, type: string, actor: string | null = 'p1') => ({
		kind,
		actor,
		raw: { type }
	});
	it('is the newest speech until a scene ends', () => {
		const a = line('speech', 'message');
		const b = line('speech', 'message', 'p2');
		expect(onStage([a, b, line('info', 'action_accepted')])).toBe(b);
		expect(onStage([a, b, line('result', 'vote_result', null)])).toBeNull();
		expect(onStage([line('heading', 'day_started', null)])).toBeNull();
	});
});

describe('ranking', () => {
	it('puts the most votes first, then the seat order', () => {
		const votes = [
			{ from: 'p1', to: 'p3' },
			{ from: 'p2', to: 'p4' },
			{ from: 'p5', to: 'p4' },
			{ from: 'p4', to: 'p2' }
		];
		expect(ranking(votes, ['p1', 'p2', 'p3', 'p4', 'p5'])).toEqual([
			{ player: 'p4', votes: 2 },
			{ player: 'p2', votes: 1 },
			{ player: 'p3', votes: 1 }
		]);
	});
});
