/** The new-match form: what it sends to `POST /matches`, and what it refuses before. */
import type { GameInfo, NewMatch } from './api.js';
import { SPEEDS } from './live.js';

export const LANGUAGES = [
	{ id: 'de', label: 'Deutsch' },
	{ id: 'en', label: 'English' }
] as const;

/** Games that have game text in a language: today only the Werewolf narrator. */
export const GAMES_WITH_LANGUAGE = new Set(['werewolf']);

export const DEFAULT_TURN_DELAY = 1;

export const BOT = 'random_bot';

export type Field =
	| 'game'
	| 'players'
	| 'seats'
	| 'seed'
	| 'language'
	| 'turn_delay'
	| 'roles'
	| 'confirm_spend'
	| 'confirm_unreliable'
	| 'match_budget_eur';

/** The Werewolf role selection: a template id, or CUSTOM for the counts of the checklist. */
export const CUSTOM = 'custom';
export const DEFAULT_TEMPLATE = 'classic';
/** Form field of the count of one role. */
export const roleField = (role: string) => `role_${role}`;

export type Parsed =
	{ ok: true; match: NewMatch } | { ok: false; errors: Partial<Record<Field, string>> };

/**
 * Read the submitted form. Every problem is reported at its field; the arena
 * checks again (settings, player counts, the cost caps) and its refusal is
 * shown too.
 *
 * `models` are the model ids a seat may take on this server; empty when the
 * server plays bots only. A match is all bots or all models: the arena does not
 * mix them yet. A model match needs the "spends money" box ticked.
 */
/**
 * The form as a match to start, or what to fix. `unreliable` are the ids the arena marks
 * unreliable: choosing one needs its own tick, on purpose possible.
 */
export function parseForm(
	form: FormData,
	games: GameInfo[],
	models: string[] = [],
	mixed = false,
	personalities = false,
	unreliable: string[] = []
): Parsed {
	const errors: Partial<Record<Field, string>> = {};
	const text = (name: string) => String(form.get(name) ?? '').trim();

	const game = games.find((g) => g.id === text('game'));
	if (!game) errors.game = 'Choose a game.';

	const players = Number(text('players'));
	if (!Number.isInteger(players)) {
		errors.players = 'Enter a whole number of players.';
	} else if (game && (players < game.min_players || players > game.max_players)) {
		errors.players = `${game.name} takes ${game.min_players} to ${game.max_players} players.`;
	}

	const seats = form.getAll('seat').map(String);
	const modelSeats = seats.filter((seat) => seat !== BOT);
	let seatModels: string[] | undefined;
	let seatSpecs: NewMatch['seats'];
	if (modelSeats.length) {
		if (!models.length) {
			errors.seats = 'This server plays random bots only; models cannot take a seat here.';
		} else if (modelSeats.some((seat) => !models.includes(seat))) {
			errors.seats = 'Choose a model from the list for every seat.';
		} else if (modelSeats.length !== seats.length && !mixed) {
			errors.seats =
				'A table is all models or all random bots on this server: it cannot mix them yet.';
		} else if (Number.isInteger(players) && seats.length !== players) {
			errors.seats = 'Choose a player for every seat.';
		} else {
			// A personality per model seat (`personality_p1`, ...), where the arena takes one.
			const played = seats.map((seat, i) =>
				personalities && seat !== BOT ? text(`personality_p${i + 1}`) : ''
			);
			if (modelSeats.length === seats.length && !played.some(Boolean)) seatModels = modelSeats;
			else
				seatSpecs = seats.map((seat, i) =>
					seat === BOT
						? { kind: 'bot' as const }
						: {
								kind: 'model' as const,
								model: seat,
								...(played[i] ? { personality: played[i] } : {})
							}
				);
			if (form.get('confirm_spend') === null) {
				errors.confirm_spend = 'A match of models spends real money: tick the box to start it.';
			}
			if (
				modelSeats.some((seat) => unreliable.includes(seat)) &&
				form.get('confirm_unreliable') === null
			) {
				errors.confirm_unreliable =
					'An unreliable model often fails or is replaced by the bot: tick the box to seat it anyway.';
			}
		}
	}

	let seed: number | undefined;
	if (text('seed') !== '') {
		seed = Number(text('seed'));
		if (!Number.isSafeInteger(seed) || seed < 0) {
			errors.seed = 'A seed is a whole number from 0, or empty for a random one.';
		}
	}

	const language = text('language') || 'de';
	if (!LANGUAGES.some((l) => l.id === language)) errors.language = 'Choose Deutsch or English.';

	const turnDelay = Number(text('turn_delay') || DEFAULT_TURN_DELAY);
	if (!SPEEDS.some((speed) => speed.turn_delay === turnDelay)) {
		errors.turn_delay = 'Choose one of the speeds.';
	}

	const settings: Record<string, unknown> = GAMES_WITH_LANGUAGE.has(game?.id ?? '')
		? { language }
		: {};
	if (game?.id === 'werewolf') {
		const mode = text('ww_mode') || DEFAULT_TEMPLATE;
		if (mode !== CUSTOM) {
			settings.template = mode;
		} else {
			const roles = selectedRoles(form);
			if (roles === null) errors.roles = 'A role count is a whole number of 0 or more.';
			else settings.roles = roles;
		}
	}

	// An optional spend limit for a match with a model: it can only lower the arena's cap,
	// which the arena checks (and refuses above it).
	const limit = text('match_budget_eur');
	if (limit !== '' && modelSeats.length) {
		const euros = Number(limit);
		if (!Number.isFinite(euros) || euros <= 0) {
			errors.match_budget_eur = 'A spend limit is a number of euros above 0, or empty for the cap.';
		} else {
			settings.match_budget_eur = euros;
		}
	}

	// The repair switch is in the form only where the arena takes the setting (GET /setup)
	// and the table has a model: then a ticked box asks for v1, a cleared one for off.
	if (form.get('answer_repair_offered') !== null && modelSeats.length) {
		settings.answer_repair = form.get('answer_repair') === null ? 'off' : 'v1';
	}

	if (Object.keys(errors).length || !game) return { ok: false, errors };
	return {
		ok: true,
		match: {
			game: game.id,
			players,
			...(seed === undefined ? {} : { seed }),
			settings,
			turn_delay: turnDelay,
			// The box says "without memory", so a form that leaves it out keeps memory on.
			memory: form.get('no_memory') === null,
			...(seatModels ? { models: seatModels, confirm_spend: true } : {}),
			...(seatSpecs ? { seats: seatSpecs, confirm_spend: true } : {})
		}
	};
}

/** The counts of the role checklist (`role_<id>` fields); null if one is not a count. */
export function selectedRoles(form: FormData): Record<string, number> | null {
	const roles: Record<string, number> = {};
	for (const [name, value] of form.entries()) {
		if (!name.startsWith('role_')) continue;
		const count = Number(String(value).trim() || 0);
		if (!Number.isInteger(count) || count < 0) return null;
		if (count > 0) roles[name.slice('role_'.length)] = count;
	}
	return roles;
}
