/** Small shared helpers of the Analytics charts: number formats and scales. */

/** A share as "35 %", or "–" when it is unknown. */
export function pct(share: number | null | undefined): string {
	return share === null || share === undefined ? '–' : `${Math.round(share * 100)} %`;
}

/** Milliseconds as "1.4 s", or "–". */
export function seconds(ms: number | null | undefined): string {
	return ms === null || ms === undefined ? '–' : `${(ms / 1000).toFixed(1)} s`;
}

/** A linear scale from [d0, d1] to [r0, r1]. */
export function scale(d0: number, d1: number, r0: number, r1: number): (v: number) => number {
	const span = d1 - d0 || 1;
	return (v) => r0 + ((v - d0) / span) * (r1 - r0);
}

/** A "nice" top for an axis: 1, 2 or 5 times a power of ten, at least `max`. */
export function niceMax(max: number): number {
	if (max <= 0) return 1;
	const power = 10 ** Math.floor(Math.log10(max));
	for (const step of [1, 2, 5, 10]) if (step * power >= max) return step * power;
	return 10 * power;
}
