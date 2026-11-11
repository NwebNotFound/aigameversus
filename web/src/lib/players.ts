/**
 * Who sits on each seat of a match, as people read it: "Gemini (gemini-flash)".
 *
 * A match record may carry `seats` (name, model and kind per seat); older
 * records and plain bot matches do not, and then the seat id is the label.
 */

export interface SeatInfo {
	name: string;
	model_id: string | null;
	kind: 'model' | 'bot';
}

export type Seats = Record<string, SeatInfo> | null | undefined;

/** "Name (model)" for a model, the name for a bot, the seat id without any info. */
export function playerLabel(seat: string, seats: Seats): string {
	const info = seats?.[seat];
	if (!info) return seat;
	return info.model_id ? `${info.name} (${info.model_id})` : info.name;
}

/** Just the name (for sentences, where the model would be noise); the seat id without info. */
export function playerName(seat: string, seats: Seats): string {
	return seats?.[seat]?.name ?? seat;
}

/** Whether real models played: any seat is a model. */
export function realModels(seats: Seats): boolean {
	return Object.values(seats ?? {}).some((info) => info.kind === 'model');
}

/** Every seat's label, for components that only need a lookup. */
export function labels(players: string[], seats: Seats): Record<string, string> {
	return Object.fromEntries(players.map((seat) => [seat, playerLabel(seat, seats)]));
}

const PLAYER_FIELDS = [
	'player',
	'caller',
	'target',
	'winner',
	'starter',
	'button',
	'from',
	'to',
	'executed',
	'model',
	'healed',
	'poisoned',
	'small_blind_player',
	'big_blind_player',
	'next_starter'
];
const PLAYER_LISTS = ['players', 'lovers', 'wolves', 'winners', 'deaths', 'eligible', 'order'];

/**
 * Event data with every seat id replaced by `name(seat)`, for sentences.
 * Values that are not seats of the match stay as they are.
 */
export function renamed(
	data: Record<string, unknown>,
	name: (seat: string) => string,
	seats: Set<string>
): Record<string, unknown> {
	const one = (value: unknown) =>
		typeof value === 'string' && seats.has(value) ? name(value) : value;
	const out: Record<string, unknown> = { ...data };
	for (const key of PLAYER_FIELDS) if (key in out) out[key] = one(out[key]);
	for (const key of PLAYER_LISTS) {
		if (Array.isArray(out[key])) out[key] = (out[key] as unknown[]).map(one);
	}
	if (out.shares && typeof out.shares === 'object') {
		out.shares = Object.fromEntries(
			Object.entries(out.shares as Record<string, unknown>).map(([k, v]) => [one(k), v])
		);
	}
	if (Array.isArray(out.hands)) {
		out.hands = (out.hands as Record<string, unknown>[]).map((h) => ({
			...h,
			player: one(h.player)
		}));
	}
	if (Array.isArray(out.placements)) {
		out.placements = (out.placements as Record<string, unknown>[]).map((p) => ({
			...p,
			player: one(p.player)
		}));
	}
	return out;
}
