/**
 * The Throne of Tokens report: types of `GET /matches/{id}/analytics` for Civ
 * (`analytics_version: "civ/1"`, docs/METRICS.md "Throne of Tokens") and the few sums the
 * Report tab shows. Everything per round, battles, orders, decisions and behaviour are null
 * in the spoiler-free view (Civ is fogged); the report then shows only the public parts.
 */

export interface Rate {
	value: number | null;
	n: number;
	of: number;
}

export interface NationSeries {
	stock: Record<string, number>[];
	income: Record<string, number>[];
	cities: number[];
	population: number[];
	armies: number[];
	units: number[];
	strength: number[];
	score: number[];
	reputation: number[];
	at_war: string[][];
}

export interface Decisions {
	moves: number;
	model_moves: number;
	fallbacks: number;
	fallback_share: Rate;
	rejected: number;
	response_ms_total: number | null;
	response_ms_mean: number | null;
	tokens_in: number | null;
	tokens_out: number | null;
	reasoning_tokens: number | null;
	retries: number;
	rate_limits: number;
	cutoffs: number;
}

export interface Orders {
	submitted: number;
	by_fallback: number;
	dropped: number;
	dropped_share: Rate;
	by_type: Record<string, { sent: number; dropped: number }>;
	reasons: { reason: string; count: number }[];
}

export interface DiplomacyEvent {
	seq: number;
	round: number;
	event: 'war_declared' | 'treaty_signed' | 'treaty_broken' | 'treaty_expired' | string;
	by?: string | null;
	on?: string | null;
	joined?: string[];
	broken?: unknown[];
	treaty?: unknown;
	parties?: string[];
	treaty_kind?: string | null;
}

export interface CivAnalytics {
	game: 'civ';
	analytics_version: string;
	spoilers: boolean;
	nations: string[];
	meta: { seats?: Record<string, string>; rounds_total?: number; [more: string]: unknown };
	series: {
		rounds: number[];
		nations: Record<string, NationSeries>;
		[more: string]: unknown;
	} | null;
	victory: {
		kind: 'round_limit' | 'domination' | 'economy' | null;
		winners: string[];
		round: number | null;
		standings: { player: string; score: number; rank: number }[];
		countdown: unknown[];
	} | null;
	battles:
		| {
				seq: number;
				round: number;
				attacker: { nation: string };
				defender: { nation: string | null };
				winner: string | null;
		  }[]
		| null;
	conquests: { seq: number; round: number; city: string; from: string; to: string }[];
	diplomacy: {
		timeline: DiplomacyEvent[];
		by_nation: Record<string, Record<string, number | null>>;
	};
	orders: Record<string, Orders> | null;
	decisions: Record<string, Decisions> | null;
	behaviour: Record<string, { tags: string[]; counts: Record<string, number> }> | null;
}

/** Whether an analytics body is the Civ report the tab draws. */
export function isCiv(body: unknown): body is CivAnalytics {
	if (!body || typeof body !== 'object') return false;
	const b = body as Record<string, unknown>;
	return b.game === 'civ' && Array.isArray(b.nations) && typeof b.diplomacy === 'object';
}

const NEUTRAL = 'neutral';

/** A list of names as English: "a", "a and b", "a, b and c". */
export function joined(items: string[]): string {
	if (items.length < 2) return items.join('');
	return `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
}

/**
 * The one sentence that says how the match went (the review's "answer first"), from the
 * victory and the standings; null while the match runs.
 */
export function verdict(data: CivAnalytics, name: (seat: string) => string): string | null {
	const v = data.victory;
	if (!v || !v.kind || !v.winners.length) return null;
	const winners = joined(v.winners.map(name));
	const verb = v.winners.length > 1 ? 'win' : 'wins';
	if (v.kind === 'domination') return `${winners} ${verb} by domination in round ${v.round}.`;
	if (v.kind === 'economy') return `${winners} ${verb} on gold in round ${v.round}.`;
	const [first, second] = [...v.standings].sort((a, b) => a.rank - b.rank);
	if (first && second && v.winners.length === 1)
		return `${winners} ${verb} on points, ${first.score} to ${second.score}.`;
	return `${winners} ${verb} on points after round ${v.round}.`;
}

export interface Tiles {
	battles: number | null;
	/** Battles between two nations, barbarians left out. */
	nationBattles: number | null;
	treaties: number;
	wars: number;
	/** Wars declared that broke a treaty in force. */
	betrayals: number;
	dropped: { n: number; of: number } | null;
	cutoffs: { n: number; of: number } | null;
}

/** The six numbers under the verdict; null where the spoiler-free view has no data. */
export function tiles(data: CivAnalytics): Tiles {
	const timeline = data.diplomacy.timeline;
	const wars = timeline.filter((e) => e.event === 'war_declared');
	const orders = data.orders ? Object.values(data.orders) : null;
	const decisions = data.decisions ? Object.values(data.decisions) : null;
	return {
		battles: data.battles ? data.battles.length : null,
		nationBattles: data.battles
			? data.battles.filter(
					(b) => b.attacker.nation !== NEUTRAL && b.defender.nation && b.defender.nation !== NEUTRAL
				).length
			: null,
		treaties: timeline.filter((e) => e.event === 'treaty_signed').length,
		wars: wars.length,
		betrayals:
			wars.filter((e) => Array.isArray(e.broken) && e.broken.length > 0).length +
			timeline.filter((e) => e.event === 'treaty_broken').length,
		dropped: orders
			? {
					n: orders.reduce((a, o) => a + o.dropped, 0),
					of: orders.reduce((a, o) => a + o.submitted + o.by_fallback, 0)
				}
			: null,
		cutoffs: decisions
			? {
					n: decisions.reduce((a, d) => a + d.cutoffs, 0),
					of: decisions.reduce((a, d) => a + d.model_moves, 0)
				}
			: null
	};
}

export interface Marker {
	round: number;
	kind: 'war' | 'betrayal' | 'conquest';
	text: string;
}

/** Key moments to mark on the score chart: wars (betrayals apart) and conquests. */
export function markers(data: CivAnalytics, name: (seat: string) => string): Marker[] {
	const out: Marker[] = [];
	for (const e of data.diplomacy.timeline) {
		if (e.event !== 'war_declared' || !e.by) continue;
		const broke = Array.isArray(e.broken) && e.broken.length > 0;
		out.push({
			round: e.round,
			kind: broke ? 'betrayal' : 'war',
			text: `${name(e.by)} declares war on ${e.on ? name(e.on) : '?'}${broke ? ', breaking a treaty' : ''}`
		});
	}
	for (const c of data.conquests)
		out.push({
			round: c.round,
			kind: 'conquest',
			text: `${c.to === NEUTRAL ? 'Barbarians' : name(c.to)} take ${c.city} from ${c.from === NEUTRAL ? 'barbarians' : name(c.from)}`
		});
	return out.sort((a, b) => a.round - b.round);
}

/** Who led on score after each round (null on a tie), for the "when did it turn" answer. */
export function leaders(data: CivAnalytics): (string | null)[] {
	const s = data.series;
	if (!s) return [];
	return s.rounds.map((_, i) => {
		let best: string | null = null;
		let top = -Infinity;
		for (const nation of data.nations) {
			const v = s.nations[nation]?.score[i] ?? -Infinity;
			if (v > top) [best, top] = [nation, v];
			else if (v === top) best = null;
		}
		return best;
	});
}

/** "p4 led from round 9 on" or "the lead changed 5 times": the answer under the score chart. */
export function leadAnswer(data: CivAnalytics, name: (seat: string) => string): string | null {
	const lead = leaders(data);
	if (!lead.length) return null;
	const changes = lead.filter(
		(l, i) => i > 0 && l !== null && l !== lead[i - 1] && lead[i - 1] !== null
	).length;
	const last = lead.at(-1);
	if (!last) return `No clear leader at the end; the lead changed ${changes} times.`;
	let from = lead.length - 1;
	while (from > 0 && lead[from - 1] === last) from--;
	const round = data.series!.rounds[from];
	return `${name(last)} led from round ${round} on${changes ? `; the lead changed ${changes} ${changes === 1 ? 'time' : 'times'}` : ''}.`;
}
