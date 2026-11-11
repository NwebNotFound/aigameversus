import { describe, expect, it } from 'vitest';
import spectator from './fixture-liars-spectator.json';
import spoilerFree from './fixture-liars-spoiler-free.json';
import {
	byRound,
	slowMoves,
	totalsOf,
	upTo,
	type LiarsAnalytics,
	type LiarsMove
} from './liars.js';

// Both fixtures are GET /matches/{id}/analytics of docs/examples/liars_deck.json (four
// real models), with and without spoilers, as the arena computes them.
const views = [
	['spectator view', spectator as unknown as LiarsAnalytics],
	['spoiler-free view', spoilerFree as unknown as LiarsAnalytics]
] as const;

describe.each(views)('the web sums like the arena (%s)', (_, data) => {
	it('gives the same totals over every move', () => {
		expect(totalsOf(data.players, data.moves, data.pulls)).toEqual(data.totals);
	});

	it('gives the same per-round cells', () => {
		expect(byRound(data.players, data.rounds, data.moves)).toEqual(data.by_round);
	});

	it('cut at the last event is the whole match', () => {
		const last = Math.max(...data.moves.map((m) => m.seq), ...data.pulls.map((p) => p.seq));
		const cut = upTo(data, last);
		expect(cut.totals).toEqual(data.totals);
		expect(cut.moves).toHaveLength(data.moves.length);
	});
});

describe('upTo', () => {
	const data = spectator as unknown as LiarsAnalytics;

	it('keeps only what happened by the step, and the totals follow', () => {
		const call = data.moves.find((m) => m.kind === 'call')!;
		const cut = upTo(data, call.seq);
		expect(cut.moves.every((m) => m.seq <= call.seq)).toBe(true);
		expect(cut.moves.at(-1)!.seq).toBe(call.seq);
		expect(cut.totals[call.player].calls).toBe(1);
		expect(cut.rounds.map((r) => r.round)).toEqual([1]);
	});

	it('before the first move there is nothing', () => {
		const cut = upTo(data, -1);
		expect(cut.moves).toEqual([]);
		expect(cut.rounds).toEqual([]);
		expect(cut.totals.p1.plays).toBe(0);
		expect(cut.totals.p1.lie_rate).toBeNull();
	});
});

describe('slowMoves', () => {
	const move = (seq: number, latency_ms: number | null) =>
		({ seq, latency_ms }) as unknown as LiarsMove;

	it('marks the moves far above the usual thinking time', () => {
		const moves = [800, 900, 1000, 1100, 950, 7000, null].map((t, i) => move(i, t));
		expect([...slowMoves(moves)]).toEqual([5]);
	});

	it('marks nothing with too few timed moves', () => {
		expect(slowMoves([move(0, 100), move(1, 9000)]).size).toBe(0);
	});
});
