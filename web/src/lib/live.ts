/**
 * What the live view does with a match log: merging the stream, which parts of the
 * board are spoilers, and how cost reads. The words of an event come from the transcript.
 */
import type { MatchEvent } from './api.js';

/**
 * The log with `incoming` added: every position once, in order.
 * A reconnect may send events again; the first copy of a position wins.
 */
export function merge(log: MatchEvent[], incoming: MatchEvent[]): MatchEvent[] {
	const bySeq = new Map(log.map((event) => [event.seq, event]));
	for (const event of incoming) if (!bySeq.has(event.seq)) bySeq.set(event.seq, event);
	return [...bySeq.values()].sort((a, b) => a.seq - b.seq);
}

/** Board fields that hide information from the players: hands, hole cards, roles, win chances. */
export const SECRET_FIELDS = new Set(['hand', 'cards', 'role', 'win_probability']);

/** Whether a board field is shown as hidden, given the spoiler setting. */
export function hidden(field: string, spoilers: boolean): boolean {
	return !spoilers && SECRET_FIELDS.has(field);
}

/**
 * Millionths of a euro as euros with four decimals, enough to tell one cheap call
 * from none. Rounded up, like the ledger: the display never shows less than was spent.
 */
export function euros(microEur: number): string {
	return `${(Math.ceil(microEur / 100) / 10_000).toFixed(4)} €`;
}

/** The delays the speed control offers, in seconds after each turn. */
export const SPEEDS = [
	{ label: 'Slow', turn_delay: 3 },
	{ label: 'Normal', turn_delay: 1 },
	{ label: 'Fast', turn_delay: 0.25 },
	{ label: 'Max', turn_delay: 0 }
];
