/** Number formatting shared by the leaderboard and profile pages. */

export const rating = (value: number) => Math.round(value).toString();

export const percent = (share: number | null) =>
	share === null ? '–' : `${Math.round(share * 100)} %`;

export const placement = (value: number | null) => (value === null ? '–' : value.toFixed(1));

export const signed = (value: number) => (value > 0 ? `+${value.toFixed(1)}` : value.toFixed(1));
