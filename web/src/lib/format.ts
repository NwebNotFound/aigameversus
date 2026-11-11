/** Number formatting shared by the leaderboard and profile pages. */

export const rating = (value: number) => Math.round(value).toString();

export const percent = (share: number | null) =>
	share === null ? '–' : `${Math.round(share * 100)} %`;

export const placement = (value: number | null) => (value === null ? '–' : value.toFixed(1));

/** A game statistic for the profile page: shares as percent, other numbers short. */
export function statValue(field: string, value: unknown): string {
	if (value === null || value === undefined) return '–';
	if (typeof value === 'boolean') return value ? 'yes' : 'no';
	if (typeof value !== 'number') return String(value);
	if (/(_rate|_share)$/.test(field)) return percent(value);
	return Number.isInteger(value) ? value.toString() : value.toFixed(2);
}

/** A field name of the statistics as a label: `call_success_rate` -> `Call success rate`. */
export const statLabel = (field: string) =>
	field.charAt(0).toUpperCase() + field.slice(1).replaceAll('_', ' ');

export const signed = (value: number) => (value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1));

/**
 * The footer's status: whether real models can play, and this month's model spend against
 * its cap when the ledger answers. Without an answer from the arena it says only what the
 * site is.
 */
export function footerLine(
	modelSeats: boolean | null,
	month: { spent_micro_eur: number; cap_micro_eur: number } | null
): string {
	const base = 'AI models play, humans watch.';
	if (modelSeats === null) return base;
	if (!modelSeats) return `${base} Bots only: real models are off on this server.`;
	if (!month) return `${base} Real models enabled.`;
	const eur = (micro: number) => (micro / 1_000_000).toFixed(2);
	return `${base} Real models enabled · EUR ${eur(month.spent_micro_eur)} of ${eur(month.cap_micro_eur)} this month.`;
}
