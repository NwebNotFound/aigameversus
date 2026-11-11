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

/** Playback speeds: milliseconds between two moments (bookkeeping is skipped, not timed). */
export const PLAY_SPEEDS = [
	{ label: '0.5×', ms: 2400 },
	{ label: '1×', ms: 1200 },
	{ label: '2×', ms: 600 },
	{ label: '4×', ms: 300 }
];

/** The link to a replay at a step, for sharing; a spoiler-free link stays spoiler-free. */
export function shareLink(
	origin: string,
	id: string,
	step: number,
	view: 'spectator' | 'spoiler-free' = 'spectator'
): string {
	const mode = view === 'spoiler-free' ? '&view=spoiler-free' : '';
	return `${origin}/replays/${encodeURIComponent(id)}?step=${step}${mode}`;
}
