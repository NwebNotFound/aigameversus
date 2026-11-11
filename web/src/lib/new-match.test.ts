import { describe, expect, it } from 'vitest';
import type { GameInfo } from './api.js';
import { BOT, parseForm } from './new-match.js';

const GAMES: GameInfo[] = [
	{ id: 'liars_deck', name: "Liar's Deck", min_players: 2, max_players: 4 },
	{ id: 'werewolf', name: 'Werewolf', min_players: 6, max_players: 16 }
];

function form(fields: Record<string, string | string[]>): FormData {
	const data = new FormData();
	for (const [name, value] of Object.entries(fields)) {
		for (const one of [value].flat()) data.append(name, one);
	}
	return data;
}

const LIARS = { game: 'liars_deck', players: '3', seat: [BOT, BOT, BOT], turn_delay: '1' };

describe('parseForm', () => {
	it('builds the start request of a bot match', () => {
		expect(parseForm(form({ ...LIARS, seed: '42', language: 'en' }), GAMES)).toEqual({
			ok: true,
			match: {
				game: 'liars_deck',
				players: 3,
				seed: 42,
				settings: {},
				turn_delay: 1,
				memory: true
			}
		});
	});

	it('leaves the seed out when it is empty, so the arena picks one', () => {
		const parsed = parseForm(form({ ...LIARS, seed: '' }), GAMES);

		expect(parsed.ok && 'seed' in parsed.match).toBe(false);
	});

	it('sends the language to Werewolf, German by default', () => {
		const werewolf = { game: 'werewolf', players: '8', seat: Array(8).fill(BOT), turn_delay: '0' };

		expect(parseForm(form(werewolf), GAMES)).toMatchObject({
			ok: true,
			match: { settings: { language: 'de' }, turn_delay: 0 }
		});
		expect(parseForm(form({ ...werewolf, language: 'en' }), GAMES)).toMatchObject({
			match: { settings: { language: 'en' } }
		});
	});

	it.each([
		[{ game: 'chess' }, 'game', 'Choose a game.'],
		[{ players: '5' }, 'players', "Liar's Deck takes 2 to 4 players."],
		[{ players: '2.5' }, 'players', 'Enter a whole number of players.'],
		[{ seed: '-1' }, 'seed', 'A seed is a whole number from 0, or empty for a random one.'],
		[{ seed: '1.5' }, 'seed', 'A seed is a whole number from 0, or empty for a random one.'],
		[{ language: 'fr' }, 'language', 'Choose Deutsch or English.'],
		[{ turn_delay: '7' }, 'turn_delay', 'Choose one of the speeds.'],
		[
			{ seat: [BOT, 'deepseek-flash', BOT] },
			'seats',
			'Models cannot take a seat yet; every seat is a random bot for now.'
		]
	])('refuses %o at its field', (change, field, message) => {
		expect(parseForm(form({ ...LIARS, ...change }), GAMES)).toEqual({
			ok: false,
			errors: { [field]: message }
		});
	});

	it('turns memory off when the box asks for a match without it', () => {
		expect(parseForm(form({ ...LIARS, no_memory: 'on' }), GAMES)).toMatchObject({
			ok: true,
			match: { memory: false }
		});
		expect(parseForm(form(LIARS), GAMES)).toMatchObject({ ok: true, match: { memory: true } });
	});
});
