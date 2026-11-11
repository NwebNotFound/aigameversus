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

export type Field = 'game' | 'players' | 'seats' | 'seed' | 'language' | 'turn_delay';

export type Parsed =
	{ ok: true; match: NewMatch } | { ok: false; errors: Partial<Record<Field, string>> };

/**
 * Read the submitted form. Every problem is reported at its field; the arena
 * checks again (settings, player counts) and its refusal is shown too.
 */
export function parseForm(form: FormData, games: GameInfo[]): Parsed {
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
	if (seats.some((seat) => seat !== BOT)) {
		errors.seats = 'Models cannot take a seat yet; every seat is a random bot for now.';
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

	if (Object.keys(errors).length || !game) return { ok: false, errors };
	return {
		ok: true,
		match: {
			game: game.id,
			players,
			...(seed === undefined ? {} : { seed }),
			settings: GAMES_WITH_LANGUAGE.has(game.id) ? { language } : {},
			turn_delay: turnDelay
		}
	};
}
