/** The replay player: steps through a stored log, one event per step. */
import type { MatchEvent } from './api.js';

/** Step n shows the first n events: 0 is before the match, `length` is its end. */
export function clampStep(step: number, length: number): number {
	if (!Number.isFinite(step)) return length;
	return Math.min(Math.max(Math.trunc(step), 0), length);
}

/** The step a share link asks for (`?step=N`); without one, the whole match. */
export function stepFromQuery(value: string | null, length: number): number {
	if (value === null || value.trim() === '') return length;
	return clampStep(Number(value), length);
}

/** Playback speeds: milliseconds between two important events. */
export const PLAY_SPEEDS = [
	{ label: '0.5×', ms: 3000 },
	{ label: '1×', ms: 1500 },
	{ label: '2×', ms: 750 },
	{ label: '4×', ms: 375 }
];

export const DEFAULT_PLAY_MS = 1500;

/** Engine bookkeeping a viewer does not need to stop at. */
const BOOKKEEPING = new Set([
	'match_started',
	'action_accepted',
	'action_rejected',
	'match_paused',
	'match_resumed'
]);

/** Secret moves worth a stop when spoilers are on (the rest is dealing and bookkeeping). */
const SECRET_MOVES = new Set([
	'cards_hidden',
	'seer_inspected',
	'wolf_vote',
	'witch_acted',
	'protected',
	'lovers_linked',
	'infection_chosen',
	'white_wolf_chose',
	'raven_chose',
	'model_chosen'
]);

/**
 * Whether play and the step buttons stop at this event: public game events,
 * talk, narration and the result always; thoughts and secret moves only with
 * spoilers on; bookkeeping and dealing never.
 */
export function isImportant(event: MatchEvent, spoilers: boolean): boolean {
	if (event.source === 'engine') {
		if (event.type === 'thought') return spoilers;
		return !BOOKKEEPING.has(event.type);
	}
	if (event.type === 'message') return event.visible_to === null || spoilers;
	if (event.visible_to === null) return true;
	return spoilers && SECRET_MOVES.has(event.type);
}

/**
 * The step after (`direction` 1) or before (-1) `step` that ends on an
 * important event; the end or the start of the log when there is none.
 */
export function nextStep(
	log: MatchEvent[],
	step: number,
	direction: 1 | -1,
	spoilers: boolean
): number {
	// Step n shows events 0..n-1, so step n "ends on" event n-1.
	for (let n = step + direction; n >= 1 && n <= log.length; n += direction) {
		if (isImportant(log[n - 1], spoilers)) return n;
	}
	return direction === 1 ? log.length : 0;
}

/** The link to a replay at a step, for sharing. */
export function shareLink(origin: string, id: string, step: number): string {
	return `${origin}/replays/${encodeURIComponent(id)}?step=${step}`;
}
