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
