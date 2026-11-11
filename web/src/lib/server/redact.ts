/**
 * What a spoiler-free page may receive. The web server proxies every arena call (D-030),
 * so it removes hidden information here, before anything reaches the browser.
 *
 * Boards are filtered by an allowlist per layout: a field that is not listed is dropped,
 * and a layout that is not listed gives no board at all. A new secret field in a plugin
 * therefore stays hidden until someone lists it here as public.
 */
import type { LiveState, MatchEvent } from '../api.js';

/** keep: public as it is. cards: hidden, sent as as many placeholders. drop-value: sent as null. */
type Rule = 'keep' | 'cards' | 'null' | Shape | [Shape];
interface Shape {
	[field: string]: Rule;
}

const PUBLIC: Record<string, Shape> = {
	card_table: {
		layout: 'keep',
		round: 'keep',
		table_card: 'keep',
		turn: 'keep',
		seats: [
			{ player: 'keep', alive: 'keep', hand: 'cards', trigger_pulls: 'keep', chambers: 'keep' }
		],
		last_play: { player: 'keep', cards: 'cards' }
	},
	poker_table: {
		layout: 'keep',
		hand: 'keep',
		street: 'keep',
		board: 'keep',
		pot: 'keep',
		side_pots: 'keep',
		button: 'keep',
		seats: [{ player: 'keep', stack: 'keep', cards: 'cards', folded: 'keep', position: 'keep' }]
	},
	player_circle: {
		layout: 'keep',
		phase: 'keep',
		night: 'keep',
		day: 'keep',
		turn: 'keep',
		seats: [{ player: 'keep', alive: 'keep', role: 'null' }]
	}
};

/** A placeholder per hidden card, so a board can draw the backs. */
export const HIDDEN_CARD = 'hidden';

function apply(rule: Rule, value: unknown): unknown {
	if (rule === 'keep') return value;
	if (rule === 'null') return null;
	if (rule === 'cards') {
		return Array.isArray(value) ? value.map((_, index) => `${HIDDEN_CARD}-${index}`) : null;
	}
	if (Array.isArray(rule)) {
		return Array.isArray(value) ? value.map((item) => apply(rule[0], item)) : null;
	}
	if (value === null || typeof value !== 'object' || Array.isArray(value)) return null;
	const source = value as Record<string, unknown>;
	return Object.fromEntries(
		Object.entries(rule)
			.filter(([field]) => field in source)
			.map(([field, inner]) => [field, apply(inner, source[field])])
	);
}

/** The board as a spoiler-free page may see it, or null for a layout without an allowlist. */
export function publicBoard(spec: Record<string, unknown> | null): Record<string, unknown> | null {
	if (!spec) return null;
	const shape = PUBLIC[String(spec.layout)];
	return shape ? (apply(shape, spec) as Record<string, unknown>) : null;
}

/** The events every player could see. Spectator-only and private events are left out. */
export function publicEvents(events: MatchEvent[]): MatchEvent[] {
	return events.filter((event) => event.visible_to === null);
}

/** A live-state snapshot for a spoiler-free page: the public board, and no seed. */
export function publicState(state: LiveState): LiveState {
	return {
		...state,
		match: { ...state.match, seed: null },
		board: { ...state.board, spec: publicBoard(state.board.spec) }
	};
}
