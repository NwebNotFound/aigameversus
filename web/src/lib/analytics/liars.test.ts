import { describe, expect, it } from 'vitest';
import spectator from './fixture-liars-spectator.json';
import spoilerFree from './fixture-liars-spoiler-free.json';
import pokerSituation from './fixture-poker-situation-only.json';
import {
	byRound,
	hasNumbers,
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
	it('gives the same totals over every move, for every number the tab shows', () => {
		const ours = totalsOf(data.players, data.moves, data.pulls, data.spoilers);
		for (const player of data.players) {
			for (const [key, value] of Object.entries(ours[player])) {
				expect(value, `${player}.${key}`).toEqual(data.totals[player][key]);
			}
		}
	});

	it('gives the same per-round cells', () => {
		expect(byRound(data.players, data.rounds, data.moves)).toEqual(data.by_round);
	});

	it('cut at the last event is the whole match', () => {
		const last = Math.max(...data.moves.map((m) => m.seq), ...data.pulls.map((p) => p.seq));
		const cut = upTo(data, last);
		for (const player of data.players) {
			expect(cut.totals[player].lies).toBe(data.totals[player].lies);
			expect(cut.totals[player].call_accuracy).toEqual(data.totals[player].call_accuracy);
		}
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
		expect(cut.totals.p1.lie_rate).toEqual({ value: null, n: 0, of: 0 });
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

describe('hasNumbers', () => {
	it("reads Poker's situation-only answer as no numbers, and never throws", () => {
		// The arena's real output for docs/examples/poker.json (#102): `situation`, no moves.
		expect(hasNumbers(pokerSituation)).toBe(false);
		const { numbers: _, ...unmarked } = pokerSituation;
		expect(hasNumbers(unmarked)).toBe(false); // an arena without the marker
		for (const body of [null, undefined, 'x', 3, {}, { game: 'liars_deck' }])
			expect(hasNumbers(body)).toBe(false);
	});

	it("takes Liar's Deck with its numbers, in both views", () => {
		expect(hasNumbers(spectator)).toBe(true);
		expect(hasNumbers(spoilerFree)).toBe(true);
		expect(hasNumbers({ ...spectator, numbers: false })).toBe(false);
	});
});
