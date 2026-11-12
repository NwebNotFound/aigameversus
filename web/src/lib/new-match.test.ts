import { describe, expect, it } from 'vitest';
import type { GameInfo } from './api.js';
import { BOT, CUSTOM, parseForm } from './new-match.js';

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
			match: { settings: { language: 'de', template: 'classic' }, turn_delay: 0 }
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
			'This server plays random bots only; models cannot take a seat here.'
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

	describe('Werewolf roles', () => {
		const WEREWOLF = {
			game: 'werewolf',
			players: '8',
			seat: Array(8).fill(BOT),
			turn_delay: '1',
			language: 'de'
		};

		it('sends a chosen template', () => {
			expect(parseForm(form({ ...WEREWOLF, ww_mode: 'chaos' }), GAMES)).toMatchObject({
				ok: true,
				match: { settings: { language: 'de', template: 'chaos' } }
			});
		});

		it('sends the counts of a custom mix, without the roles left at 0', () => {
			const custom = {
				...WEREWOLF,
				ww_mode: CUSTOM,
				role_werewolf: '2',
				role_seer: '1',
				role_hunter: '0',
				role_witch: ''
			};

			const parsed = parseForm(form(custom), GAMES);

			expect(parsed).toMatchObject({ ok: true });
			expect(parsed.ok && parsed.match.settings).toEqual({
				language: 'de',
				roles: { werewolf: 2, seer: 1 }
			});
		});

		it('ignores the checklist while a template is chosen', () => {
			const parsed = parseForm(form({ ...WEREWOLF, ww_mode: 'classic', role_seer: '1' }), GAMES);

			expect(parsed.ok && parsed.match.settings).toEqual({ language: 'de', template: 'classic' });
		});

		it.each(['-1', '1.5', 'two'])('refuses the count %s at the roles', (count) => {
			const custom = { ...WEREWOLF, ww_mode: CUSTOM, role_werewolf: count };

			expect(parseForm(form(custom), GAMES)).toEqual({
				ok: false,
				errors: { roles: 'A role count is a whole number of 0 or more.' }
			});
		});
	});

	describe('model seats', () => {
		const MODELS = ['deepseek-flash', 'qwen-flash'];
		const THREE = { ...LIARS, seat: ['deepseek-flash', 'qwen-flash', 'deepseek-flash'] };

		it('starts a match of models when the spend box is ticked', () => {
			expect(parseForm(form({ ...THREE, confirm_spend: 'on' }), GAMES, MODELS)).toMatchObject({
				ok: true,
				match: {
					players: 3,
					models: ['deepseek-flash', 'qwen-flash', 'deepseek-flash'],
					confirm_spend: true
				}
			});
		});

		it('refuses a match of models without the spend box', () => {
			expect(parseForm(form(THREE), GAMES, MODELS)).toEqual({
				ok: false,
				errors: {
					confirm_spend: 'A match of models spends real money: tick the box to start it.'
				}
			});
		});

		it.each([
			[
				[BOT, 'qwen-flash', BOT],
				'A table is all models or all random bots on this server: it cannot mix them yet.'
			],
			[['qwen-flash', 'gpt-x', 'qwen-flash'], 'Choose a model from the list for every seat.']
		])('refuses the seats %o', (seat, message) => {
			expect(parseForm(form({ ...LIARS, seat, confirm_spend: 'on' }), GAMES, MODELS)).toEqual({
				ok: false,
				errors: { seats: message }
			});
		});

		it('sends a mixed table as seats where the arena takes them', () => {
			const parsed = parseForm(
				form({ ...LIARS, seat: [BOT, 'qwen-flash', BOT], confirm_spend: 'on' }),
				GAMES,
				MODELS,
				true
			);

			expect(parsed).toMatchObject({
				ok: true,
				match: {
					players: 3,
					seats: [{ kind: 'bot' }, { kind: 'model', model: 'qwen-flash' }, { kind: 'bot' }],
					confirm_spend: true
				}
			});
			expect(parsed.ok && 'models' in parsed.match).toBe(false);
		});

		it('still sends an all-model table as models', () => {
			const parsed = parseForm(form({ ...THREE, confirm_spend: 'on' }), GAMES, MODELS, true);

			expect(parsed.ok && parsed.match.models).toEqual(THREE.seat);
			expect(parsed.ok && 'seats' in parsed.match).toBe(false);
		});

		it('asks for a second tick when an unreliable model takes a seat', () => {
			const ticked = { ...THREE, confirm_spend: 'on' };

			expect(parseForm(form(ticked), GAMES, MODELS, false, ['qwen-flash'])).toEqual({
				ok: false,
				errors: {
					confirm_unreliable:
						'An unreliable model often fails or is replaced by the bot: tick the box to seat it anyway.'
				}
			});
			expect(
				parseForm(form({ ...ticked, confirm_unreliable: 'on' }), GAMES, MODELS, false, [
					'qwen-flash'
				])
			).toMatchObject({ ok: true });
			expect(parseForm(form(ticked), GAMES, MODELS, false, ['other/model'])).toMatchObject({
				ok: true
			});
		});

		it('sends no models and no spend for a bot match', () => {
			const parsed = parseForm(form({ ...LIARS, confirm_spend: 'on' }), GAMES, MODELS);

			expect(parsed.ok && 'models' in parsed.match).toBe(false);
			expect(parsed.ok && 'confirm_spend' in parsed.match).toBe(false);
		});
	});
});
