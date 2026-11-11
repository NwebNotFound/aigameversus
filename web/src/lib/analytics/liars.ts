/**
 * Liar's Deck analytics for the Analytics tab: the shape of `GET /matches/{id}/analytics`
 * (arena/analytics/liars_deck.py, docs/METRICS.md) and what the tab derives from it.
 * The arena computes every number; the web only cuts the moves to the replay's step and
 * sums them again for that cut.
 */

export interface LiarsMove {
	seq: number;
	round: number;
	player: string;
	kind: 'play' | 'call';
	index: number;
	cards?: number;
	cards_left?: number;
	/** null when the play's cards were never shown (spoiler-free). */
	honest?: boolean | null;
	called?: boolean;
	target?: string;
	automatic?: boolean;
	correct?: boolean | null;
	fallback: boolean | null;
	/** The player's own revolver risk at that moment; public, in both views. */
	risk?: number | null;
	latency_ms: number | null;
	tokens_in: number | null;
	tokens_out: number | null;
	reasoning_tokens: number | null;
	retries: number | null;
	/** Answers of this move the engine refused before one counted: answer quality, not drama. */
	rejected?: number | null;
}

export interface LiarsPull {
	seq: number;
	round: number;
	player: string;
	pull: number;
	live: boolean;
	/** Chance the pull fires: live chambers over chambers left; public. */
	risk: number | null;
}

/** A rate as the arena sends it: the value (null with nothing to count) and its n. */
export interface Rate {
	value: number | null;
	n: number;
	of: number;
}

/** The totals the tab shows; the arena sends more (docs/METRICS.md), all read as they come. */
export interface LiarsTotals {
	plays: number;
	plays_known: number;
	honest: number;
	lies: number;
	lies_called: number;
	/** Spoilers only (null without): over revealed plays it would lean towards called plays. */
	lie_rate: Rate | null;
	calls: number;
	calls_correct: number;
	calls_wrong: number;
	call_accuracy: Rate;
	pulls: number;
	pulls_survived: number;
	fallbacks: number;
	/** Refused answers over all the player's moves, each fixed on a retry or by a fallback. */
	rejected: number;
	response_ms_total: number | null;
	response_ms_mean: number | null;
	[more: string]: unknown;
}

export interface LiarsAnalytics {
	game: 'liars_deck';
	spoilers: boolean;
	events: number;
	players: string[];
	moves: LiarsMove[];
	pulls: LiarsPull[];
	rounds: { round: number; table_card: string; players: string[] }[];
	totals: Record<string, LiarsTotals>;
	by_round: {
		round: number;
		players: Record<
			string,
			{ honest: number; lies: number; unknown: number; calls: number; fallbacks: number }
		>;
	}[];
	meta?: Record<string, unknown>;
}

/** The analytics as they stood after the event at `lastSeq` (all of them when null). */
export function upTo(data: LiarsAnalytics, lastSeq: number | null): LiarsAnalytics {
	if (lastSeq === null) return data;
	const moves = data.moves.filter((m) => m.seq <= lastSeq);
	const pulls = data.pulls.filter((p) => p.seq <= lastSeq);
	const lastRound = Math.max(0, ...moves.map((m) => m.round), ...pulls.map((p) => p.round));
	const rounds = data.rounds.filter((r) => r.round <= lastRound);
	return {
		...data,
		moves,
		pulls,
		rounds,
		totals: totalsOf(data.players, moves, pulls, data.spoilers),
		by_round: byRound(data.players, rounds, moves)
	};
}

const sum = (values: (number | null)[]) => {
	const known = values.filter((v): v is number => v !== null);
	return known.length ? known.reduce((a, b) => a + b, 0) : null;
};

const rate = (n: number, of: number): Rate => ({ value: of ? n / of : null, n, of });

/**
 * The totals the tab shows, by the rules of docs/METRICS.md, for a replay cut part-way:
 * skill numbers count the model's own moves (fallbacks apart), the lie rate needs the
 * hidden cards. Summed over every move they equal the arena's (tested); the arena's other
 * numbers are not recomputed here.
 */
export function totalsOf(
	players: string[],
	moves: LiarsMove[],
	pulls: LiarsPull[],
	spoilers: boolean
): Record<string, LiarsTotals> {
	return Object.fromEntries(
		players.map((player) => {
			const mine = moves.filter((m) => m.player === player);
			const own = mine.filter((m) => !m.fallback);
			const plays = own.filter((m) => m.kind === 'play');
			const known = plays.filter((m) => m.honest !== null && m.honest !== undefined);
			const lies = known.filter((m) => m.honest === false);
			const calls = own.filter((m) => m.kind === 'call');
			const judged = calls.filter((m) => m.correct !== null && m.correct !== undefined);
			const correct = judged.filter((m) => m.correct).length;
			const times = mine.map((m) => m.latency_ms).filter((v): v is number => v !== null);
			const total = times.length ? times.reduce((a, b) => a + b, 0) : null;
			const myPulls = pulls.filter((p) => p.player === player);
			return [
				player,
				{
					plays: plays.length,
					plays_known: known.length,
					honest: known.length - lies.length,
					lies: lies.length,
					lies_called: lies.filter((m) => m.called).length,
					lie_rate: spoilers ? rate(lies.length, known.length) : null,
					calls: calls.length,
					calls_correct: correct,
					calls_wrong: judged.length - correct,
					call_accuracy: rate(correct, judged.length),
					pulls: myPulls.length,
					pulls_survived: myPulls.filter((p) => !p.live).length,
					fallbacks: mine.filter((m) => m.fallback).length,
					rejected: mine.reduce((sum, m) => sum + (m.rejected ?? 0), 0),
					response_ms_total: total,
					response_ms_mean: total === null ? null : total / times.length
				}
			];
		})
	);
}

/** Honest, lie, unknown and call counts per round and player, for the heatmap. */
export function byRound(
	players: string[],
	rounds: { round: number }[],
	moves: LiarsMove[]
): LiarsAnalytics['by_round'] {
	return rounds.map(({ round }) => ({
		round,
		players: Object.fromEntries(
			players.map((player) => {
				const all = moves.filter((m) => m.round === round && m.player === player);
				const mine = all.filter((m) => !m.fallback);
				const plays = mine.filter((m) => m.kind === 'play');
				return [
					player,
					{
						honest: plays.filter((m) => m.honest === true).length,
						lies: plays.filter((m) => m.honest === false).length,
						unknown: plays.filter((m) => m.honest === null || m.honest === undefined).length,
						calls: mine.filter((m) => m.kind === 'call').length,
						fallbacks: all.filter((m) => m.fallback).length
					}
				];
			})
		)
	}));
}

/**
 * Moves whose response took unusually long: above the median plus 2.5 times the median absolute
 * deviation of all timed moves (a robust cut that a single huge outlier does not move).
 */
export function slowMoves(moves: LiarsMove[]): Set<number> {
	const times = moves.map((m) => m.latency_ms).filter((v): v is number => v !== null);
	if (times.length < 4) return new Set();
	const median = (xs: number[]) => {
		const s = [...xs].sort((a, b) => a - b);
		const mid = Math.floor(s.length / 2);
		return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
	};
	const m = median(times);
	const mad = median(times.map((t) => Math.abs(t - m))) || 1;
	return new Set(
		moves.filter((x) => x.latency_ms !== null && x.latency_ms > m + 2.5 * mad).map((x) => x.seq)
	);
}
