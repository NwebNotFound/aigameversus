/** The replay player: steps through a stored log, one event per step. */

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

/** Playback speeds: milliseconds between two steps. */
export const PLAY_SPEEDS = [
	{ label: '0.5×', ms: 1000 },
	{ label: '1×', ms: 500 },
	{ label: '2×', ms: 250 },
	{ label: '4×', ms: 125 }
];

export const DEFAULT_PLAY_MS = 500;

/** The link to a replay at a step, for sharing. */
export function shareLink(origin: string, id: string, step: number): string {
	return `${origin}/replays/${encodeURIComponent(id)}?step=${step}`;
}
