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
