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
	latency_ms: number | null;
	tokens_in: number | null;
	tokens_out: number | null;
	reasoning_tokens: number | null;
	retries: number | null;
}

export interface LiarsPull {
	seq: number;
	round: number;
	player: string;
	pull: number;
	live: boolean;
	/** Chance the pull fires; null without spoilers. */
	risk: number | null;
}

export interface LiarsTotals {
	plays: number;
	plays_known: number;
	honest: number;
	lies: number;
	lies_called: number;
	lie_rate: number | null;
	calls: number;
	calls_correct: number;
	calls_wrong: number;
	call_accuracy: number | null;
	cards_claimed: number;
	pulls: number;
	pulls_survived: number;
	fallbacks: number;
	thinking_ms_total: number | null;
	thinking_ms_mean: number | null;
	tokens_in: number | null;
	tokens_out: number | null;
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
		players: Record<string, { honest: number; lies: number; unknown: number; calls: number }>;
	}[];
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
		totals: totalsOf(data.players, moves, pulls),
		by_round: byRound(data.players, rounds, moves)
	};
}

const sum = (values: (number | null)[]) => {
	const known = values.filter((v): v is number => v !== null);
	return known.length ? known.reduce((a, b) => a + b, 0) : null;
};

/**
 * The per-player totals of docs/METRICS.md over the given moves and pulls: the same sums the
 * arena makes, for a replay that stopped part-way.
 */
export function totalsOf(
	players: string[],
	moves: LiarsMove[],
	pulls: LiarsPull[]
): Record<string, LiarsTotals> {
	return Object.fromEntries(
		players.map((player) => {
			const plays = moves.filter((m) => m.player === player && m.kind === 'play');
			const known = plays.filter((m) => m.honest !== null && m.honest !== undefined);
			const lies = known.filter((m) => m.honest === false);
			const chosen = moves.filter((m) => m.player === player && m.kind === 'call' && !m.automatic);
			const judged = chosen.filter((m) => m.correct !== null && m.correct !== undefined);
			const correct = judged.filter((m) => m.correct).length;
			const own = moves.filter((m) => m.player === player);
			const latencies = own.map((m) => m.latency_ms);
			const thinking = sum(latencies);
			const timed = latencies.filter((v) => v !== null).length;
			const mine = pulls.filter((p) => p.player === player);
			return [
				player,
				{
					plays: plays.length,
					plays_known: known.length,
					honest: known.length - lies.length,
					lies: lies.length,
					lies_called: lies.filter((m) => m.called).length,
					lie_rate: known.length ? lies.length / known.length : null,
					calls: chosen.length,
					calls_correct: correct,
					calls_wrong: judged.length - correct,
					call_accuracy: judged.length ? correct / judged.length : null,
					cards_claimed: plays.reduce((a, m) => a + (m.cards ?? 0), 0),
					pulls: mine.length,
					pulls_survived: mine.filter((p) => !p.live).length,
					fallbacks: own.filter((m) => m.fallback).length,
					thinking_ms_total: thinking,
					thinking_ms_mean: thinking === null ? null : thinking / timed,
					tokens_in: sum(own.map((m) => m.tokens_in)),
					tokens_out: sum(own.map((m) => m.tokens_out))
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
				const mine = moves.filter((m) => m.round === round && m.player === player);
				const plays = mine.filter((m) => m.kind === 'play');
				return [
					player,
					{
						honest: plays.filter((m) => m.honest === true).length,
						lies: plays.filter((m) => m.honest === false).length,
						unknown: plays.filter((m) => m.honest === null || m.honest === undefined).length,
						calls: mine.filter((m) => m.kind === 'call').length
					}
				];
			})
		)
	}));
}

/**
 * Moves that took unusually long: above the median plus 2.5 times the median absolute
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
