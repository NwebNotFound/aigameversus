import { describe, expect, it } from 'vitest';
import spectator from './fixture-civ-spectator.json';
import spoilerFree from './fixture-civ-spoiler-free.json';
import {
	isCiv,
	joined,
	leadAnswer,
	leaders,
	markers,
	tiles,
	verdict,
	type CivAnalytics
} from './civ.js';

// A real match (9e889fca: glm-flash, deepseek-flash-civ, gpt-luna, claude-haiku; 20 rounds).
const full = spectator as unknown as CivAnalytics;
const open = spoilerFree as unknown as CivAnalytics;
const seats = full.meta.seats ?? {};
const name = (seat: string) => seats[seat] ?? seat;

describe('isCiv', () => {
	it('takes both views of a Civ answer, and nothing else', () => {
		expect(isCiv(full)).toBe(true);
		expect(isCiv(open)).toBe(true);
		expect(isCiv({ game: 'liars_deck', nations: [] })).toBe(false);
		expect(isCiv(null)).toBe(false);
	});
});

describe('verdict', () => {
	it('says who won and how, from the standings', () => {
		const winner = name(full.victory!.winners[0]);
		const [first, second] = [...full.victory!.standings].sort((a, b) => a.rank - b.rank);
		expect(verdict(full, name)).toBe(
			`${winner} wins on points, ${first.score} to ${second.score}.`
		);
	});

	it('is the same sentence in the spoiler-free view (the result is public)', () => {
		expect(verdict(open, name)).toBe(verdict(full, name));
	});

	it('names several winners in English', () => {
		expect(joined(['a', 'b', 'c'])).toBe('a, b and c');
	});
});

describe('tiles', () => {
	it('counts battles, treaties, wars, dropped orders and cut-off answers with their n', () => {
		const t = tiles(full);
		expect(t.battles).toBe(full.battles!.length);
		expect(t.treaties).toBe(
			full.diplomacy.timeline.filter((e) => e.event === 'treaty_signed').length
		);
		const dropped = Object.values(full.orders!).reduce((a, o) => a + o.dropped, 0);
		expect(t.dropped!.n).toBe(dropped);
		expect(t.dropped!.of).toBeGreaterThanOrEqual(dropped);
		expect(t.cutoffs!.of).toBe(
			Object.values(full.decisions!).reduce((a, d) => a + d.model_moves, 0)
		);
	});

	it('leaves what the spoiler-free view hides as null, and keeps the public counts', () => {
		const t = tiles(open);
		expect(t.battles).toBeNull();
		expect(t.dropped).toBeNull();
		expect(t.cutoffs).toBeNull();
		expect(t.treaties).toBe(tiles(full).treaties);
		expect(t.wars).toBe(tiles(full).wars);
	});
});

describe('leaders and markers', () => {
	it('has one leader entry per round, and the winner leads at the end', () => {
		expect(leaders(full)).toHaveLength(full.series!.rounds.length);
		expect(leaders(full).at(-1)).toBe(full.victory!.winners[0]);
		expect(leadAnswer(full, name)).toMatch(
			new RegExp(`^${name(full.victory!.winners[0])} led from round \\d+ on`)
		);
		expect(leaders(open)).toEqual([]);
	});

	it('marks wars and conquests in round order', () => {
		const m = markers(full, name);
		expect(m.map((x) => x.round)).toEqual([...m.map((x) => x.round)].sort((a, b) => a - b));
		expect(m.filter((x) => x.kind !== 'conquest')).toHaveLength(tiles(full).wars);
	});
});
