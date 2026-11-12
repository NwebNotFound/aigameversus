/**
 * What a spoiler-free page may receive. The web server proxies every arena call (D-030),
 * so it removes hidden information here, before anything reaches the browser.
 *
 * Boards are filtered by an allowlist per layout: a field that is not listed is dropped,
 * and a layout that is not listed gives no board at all. A new secret field in a plugin
 * therefore stays hidden until someone lists it here as public.
 */
import type { LiveState, MatchEvent, Transcript, TranscriptLine } from '../api.js';
import { attempts } from '../viewer.js';

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

/** Match settings every player knows. Anything else (an unknown key) is dropped. */
const PUBLIC_SETTINGS = new Set([
	'language',
	'variant',
	'duplicate',
	'hand_size',
	'captain',
	'roles_public'
]);

/**
 * The settings a spoiler-free page may see. A Werewolf role mix (`roles`, or the `template`
 * it was drawn from) is public only when the match made the role list public.
 */
export function publicSettings(settings: Record<string, unknown>): Record<string, unknown> {
	const rolesPublic = settings.roles_public === true;
	return Object.fromEntries(
		Object.entries(settings).filter(
			([key]) =>
				PUBLIC_SETTINGS.has(key) || (rolesPublic && (key === 'roles' || key === 'template'))
		)
	);
}

/**
 * A spoiler-free transcript (already asked for with `spoilers=false`) with public settings
 * only: the opening line's raw event carries the match settings, role mix included.
 */
export function publicTranscript(transcript: Transcript): Transcript {
	return {
		...transcript,
		lines: transcript.lines.map((line) => {
			const data = line.raw?.data as Record<string, unknown> | undefined;
			const settings = data?.settings;
			if (!settings || typeof settings !== 'object') return line;
			const safe = publicSettings(settings as Record<string, unknown>);
			return { ...line, raw: { ...line.raw, data: { ...data, settings: safe } } };
		})
	};
}

/**
 * A repaired move is marked in the spoiler-free view too, but only that it was repaired, by
 * which tier and with what probability: read from the spectator lines (`decision`,
 * `action_accepted`, never sent on) and put on the public line of the same move. The
 * refused call, its arguments and the error text stay here, as they can name hidden cards.
 */
export function withRepairMarks(open: Transcript, spectator: TranscriptLine[]): Transcript {
	const bySeq = new Map<number, { tier: 1 | 2; p: number | null }>();
	for (const [line, mark] of attempts(spectator).marks)
		if (mark.repair && line.seq !== null)
			bySeq.set(line.seq, { tier: mark.repair.tier, p: mark.repair.p });
	if (bySeq.size === 0) return open;
	return {
		...open,
		lines: open.lines.map((line) =>
			line.seq !== null && bySeq.has(line.seq) ? { ...line, repair: bySeq.get(line.seq) } : line
		)
	};
}

/** A live-state snapshot for a spoiler-free page: the public board and settings, and no seed. */
export function publicState(state: LiveState): LiveState {
	return {
		...state,
		match: { ...state.match, seed: null, settings: publicSettings(state.match.settings) },
		board: { ...state.board, spec: publicBoard(state.board.spec) }
	};
}
