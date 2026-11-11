/**
 * What the live view does with a match log: which column an event goes to,
 * how it reads, and which parts of the board are spoilers.
 */
import type { MatchEvent } from './api.js';

/** Middle column: what every player sees. Right column: thoughts and private events. */
export type Column = 'public' | 'behind';

export function columnOf(event: MatchEvent): Column {
	return event.visible_to === null ? 'public' : 'behind';
}

/** The players an event is about: its author or subject, and who may see it. */
export function playersOf(event: MatchEvent): string[] {
	const players = new Set(event.visible_to ?? []);
	for (const key of ['player', 'caller', 'target']) {
		const value = event.data[key];
		if (typeof value === 'string') players.add(value);
	}
	return [...players];
}

export type Line =
	| { kind: 'message'; player: string; text: string }
	| { kind: 'thought'; player: string; text: string }
	| { kind: 'narration'; text: string }
	| { kind: 'event'; player: string | null; title: string; details: string };

/** One event as the live view shows it. Player text stays text: it is never rendered as HTML. */
export function describe(event: MatchEvent): Line {
	const { type, data } = event;
	const player = typeof data.player === 'string' ? data.player : null;
	const text = typeof data.text === 'string' ? data.text : null;
	if (type === 'message' && player && text !== null) return { kind: 'message', player, text };
	if (type === 'thought' && player && text !== null) return { kind: 'thought', player, text };
	if (type === 'narration' && text !== null) return { kind: 'narration', text };
	const rest = Object.entries(data).filter(([key]) => key !== 'player');
	return {
		kind: 'event',
		player,
		title: type.replaceAll('_', ' '),
		details: rest.map(([key, value]) => `${key.replaceAll('_', ' ')}: ${show(value)}`).join(' · ')
	};
}

function show(value: unknown): string {
	if (Array.isArray(value)) return value.map(show).join(', ');
	if (value !== null && typeof value === 'object') return JSON.stringify(value);
	return String(value);
}

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
