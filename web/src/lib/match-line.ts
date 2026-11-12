/**
 * One running match as a list row reads it: who plays (display names and colour keys),
 * how far it is, what it cost so far. Built from the match record, the public board and
 * the cost, so a list says "Liar's Deck · gpt-luna, glm-flash · round 5 · 0.0120 €".
 */
import type { BatchSummary, MatchBatch, MatchSummary, SetupOptions } from './api.js';
import { euros } from './live.js';
import { colourKey, mergeSeats, seatName } from './viewer.js';

export interface LineSeat {
	seat: string;
	name: string;
	colourKey: string;
	kind: 'model' | 'bot' | undefined;
}

export interface MatchLine {
	seats: LineSeat[];
	/** Whether a model plays any seat. */
	real: boolean;
	/** "round 5", "hand 3", "night 2", "day 2"; null before the first one or for other games. */
	progress: string | null;
	/** Millionths of a euro so far; null while the cost is not known. */
	cost_micro_eur: number | null;
}

const count = (value: unknown): number | null =>
	typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null;

/** How far a match is, from public fields of its board only. */
export function progressOf(spec: Record<string, unknown> | null | undefined): string | null {
	if (!spec) return null;
	if (spec.layout === 'card_table') {
		const round = count(spec.round);
		return round ? `round ${round}` : null;
	}
	if (spec.layout === 'poker_table') {
		const hand = count(spec.hand);
		return hand ? `hand ${hand}` : null;
	}
	if (spec.layout === 'player_circle') {
		// A Werewolf day carries the number of the night before it.
		const night = count(spec.night);
		if (!night) return null;
		return spec.phase === 'night' ? `night ${night}` : `day ${night}`;
	}
	return null;
}

export function matchLine(
	match: MatchSummary,
	spec: Record<string, unknown> | null | undefined,
	cost: number | null | undefined,
	roster: SetupOptions['models'] = []
): MatchLine {
	const players = mergeSeats(match.players, match.seats, undefined, roster);
	const seats = match.players.map((seat) => ({
		seat,
		name: seatName(seat, players),
		colourKey: colourKey(seat, players),
		kind: players[seat]?.kind
	}));
	return {
		seats,
		real: seats.some((s) => s.kind === 'model'),
		progress: progressOf(spec),
		cost_micro_eur: cost ?? null
	};
}

/**
 * A batch as one list row: "E1 league A2 · 14 of 120 done, 4 running · 0.3100 € of 3.00 €".
 * Without its summary (the arena did not answer) only what the match records carry.
 */
export function batchLine(
	batch: MatchBatch,
	summary: BatchSummary | null,
	runningHere: number
): string {
	const parts = [summary?.label ?? batch.label];
	const of = summary?.of ?? batch.of;
	const running = summary?.statuses.running ?? runningHere;
	if (summary) {
		const done = summary.statuses.finished ?? 0;
		parts.push(`${done}${of ? ` of ${of}` : ''} done, ${running} running`);
	} else {
		parts.push(`${running} running`);
	}
	const budget = summary?.budget_eur ?? batch.budget_eur;
	if (summary && summary.cost_micro_eur !== null) {
		const spent = euros(summary.cost_micro_eur);
		parts.push(budget === null ? spent : `${spent} of ${budget.toFixed(2)} €`);
	}
	return parts.join(' · ');
}

export interface ListEntry<T> {
	/** null: a match on its own. */
	batch: MatchBatch | null;
	items: T[];
}

/** Matches of one batch together, in the place of its first; others stay as they are. */
export function groupByBatch<T>(items: T[], batchOf: (item: T) => MatchBatch | null | undefined) {
	const entries: ListEntry<T>[] = [];
	const byId = new Map<string, ListEntry<T>>();
	for (const item of items) {
		const batch = batchOf(item) ?? null;
		if (batch === null) {
			entries.push({ batch: null, items: [item] });
			continue;
		}
		const known = byId.get(batch.id);
		if (known) known.items.push(item);
		else {
			const entry = { batch, items: [item] };
			byId.set(batch.id, entry);
			entries.push(entry);
		}
	}
	return entries;
}
