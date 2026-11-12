import { describe, expect, it } from 'vitest';
import {
	claimsUpTo,
	mostSuspected,
	suspicion,
	type Accusation,
	type Claim
} from './werewolfIntel.js';

const claim = (seq: number, player: string, role: string, extra: Partial<Claim> = {}): Claim => ({
	seq,
	player,
	role,
	changed_from: null,
	counterclaimed_by: [],
	disproved: false,
	true_role: null,
	lie: null,
	...extra
});
const acc = (
	seq: number,
	by: string,
	target: string,
	source: Accusation['source']
): Accusation => ({
	seq,
	by,
	target,
	source
});

describe('claimsUpTo', () => {
	it("keeps each player's claims in order, up to the moment on screen", () => {
		const claims = [
			claim(10, 'p1', 'villager'),
			claim(20, 'p2', 'seer'),
			claim(30, 'p1', 'hunter')
		];
		expect(
			claimsUpTo(claims, 25)
				.get('p1')!
				.map((c) => c.role)
		).toEqual(['villager']);
		expect(
			claimsUpTo(claims, null)
				.get('p1')!
				.map((c) => c.role)
		).toEqual(['villager', 'hunter']);
		expect(claimsUpTo(claims, 5).size).toBe(0);
	});
});

describe('suspicion', () => {
	it('counts sentences and votes per accuser and target, and never self-accusation', () => {
		const { cells, max } = suspicion(
			[
				acc(1, 'p1', 'p3', 'speech'),
				acc(2, 'p1', 'p3', 'speech'),
				acc(3, 'p1', 'p3', 'vote'),
				acc(4, 'p2', 'p1', 'speech'),
				acc(5, 'p2', 'p2', 'speech'),
				acc(99, 'p4', 'p1', 'vote')
			],
			50
		);
		expect(cells.get('p1')!.get('p3')).toEqual({ speech: 2, votes: 1 });
		expect(cells.get('p2')!.has('p2')).toBe(false);
		expect(cells.has('p4')).toBe(false);
		expect(max).toBe(3);
	});
});

describe('mostSuspected', () => {
	it('names the most accused, and nobody on a tie', () => {
		expect(mostSuspected([acc(1, 'p1', 'p3', 'speech'), acc(2, 'p2', 'p3', 'vote')], null)).toBe(
			'p3'
		);
		expect(mostSuspected([acc(1, 'p1', 'p3', 'speech'), acc(2, 'p2', 'p1', 'vote')], null)).toBe(
			null
		);
	});
});
