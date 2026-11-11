import { describe, expect, it } from 'vitest';
import type { MatchEvent } from './api.js';
import { eventText, matchLang, ordinal, placementsText } from './event-text.js';

function game(type: string, data: Record<string, unknown>): MatchEvent {
	return { seq: 0, source: 'game', type, data, visible_to: null };
}

function engine(type: string, data: Record<string, unknown>): MatchEvent {
	return { seq: 0, source: 'engine', type, data, visible_to: null };
}

describe('placements', () => {
	const placements = [
		{ player: 'p4', rank: 1 },
		{ player: 'p2', rank: 2 },
		{ player: 'p3', rank: 2 },
		{ player: 'p1', rank: 4 }
	];

	it('reads as a result, shared ranks together', () => {
		expect(placementsText(placements, 'en')).toBe('1st p4 · 2nd p2, p3 · 4th p1');
		expect(placementsText(placements, 'de')).toBe('1. p4 · 2. p2, p3 · 4. p1');
	});

	it('is the result line of a finished match, not JSON', () => {
		const finished = engine('match_finished', { placements });

		expect(eventText('poker', finished, 'en')).toBe('Result: 1st p4 · 2nd p2, p3 · 4th p1');
		expect(eventText('poker', finished, 'de')).toBe('Ergebnis: 1. p4 · 2. p2, p3 · 4. p1');
	});

	it.each([
		[1, '1st'],
		[2, '2nd'],
		[3, '3rd'],
		[4, '4th'],
		[11, '11th'],
		[12, '12th'],
		[21, '21st']
	])('ordinal %i is %s', (rank, text) => {
		expect(ordinal(rank, 'en')).toBe(text);
	});
});

describe("Liar's Deck", () => {
	it.each([
		[
			game('liar_called', { caller: 'p2', target: 'p1', automatic: false }),
			'p2 calls p1 a liar!',
			'p2 nennt p1 einen Lügner!'
		],
		[
			game('cards_revealed', { player: 'p1', cards: ['K4', 'Q3'], honest: false, devil: false }),
			'The cards of p1 show a bluff: K4 and Q3.',
			'Die Karten von p1 zeigen einen Bluff: K4 und Q3.'
		],
		[
			game('trigger_pulled', { player: 'p1', pull: 2, live: false }),
			'p1 pulls the trigger: click. Pull 2.',
			'p1 drückt ab: klick. Versuch 2.'
		],
		[
			game('cards_played', { player: 'p3', count: 1 }),
			'p3 plays 1 card face down.',
			'p3 legt 1 Karte verdeckt.'
		],
		[
			game('round_started', { round: 2, table_card: 'queen', starter: 'p2' }),
			'Round 2 starts. Table card: queen; p2 begins.',
			'Runde 2 beginnt. Tischkarte: queen; p2 fängt an.'
		]
	])('%o', (event, en, de) => {
		expect(eventText('liars_deck', event, 'en')).toBe(en);
		expect(eventText('liars_deck', event, 'de')).toBe(de);
	});
});

describe('Poker', () => {
	it.each([
		[
			game('bet_action', { player: 'p1', kind: 'raise', street: 'flop', to: 120, added: 100 }),
			'p1 raises to 120.',
			'p1 erhöht auf 120.'
		],
		[
			game('bet_action', { player: 'p2', kind: 'call', street: 'flop', to: 120, added: 120 }),
			'p2 calls.',
			'p2 geht mit.'
		],
		[
			game('street_started', { street: 'flop', order: ['p1', 'p2'], cards: ['Ah', 'Kd', '7c'] }),
			'The flop: Ah, Kd and 7c.',
			'Der Flop: Ah, Kd und 7c.'
		],
		[
			game('pot_awarded', { amount: 300, eligible: ['p1', 'p2'], shares: { p1: 300, p2: 0 } }),
			'Pot of 300 won: p1 300.',
			'Pot von 300 gewonnen: p1 300.'
		]
	])('%o', (event, en, de) => {
		expect(eventText('poker', event, 'en')).toBe(en);
		expect(eventText('poker', event, 'de')).toBe(de);
	});
});

describe('Werewolf', () => {
	it.each([
		[game('night_started', { night: 2 }), 'Night 2 falls.', 'Nacht 2 bricht herein.'],
		[
			game('morning_started', { night: 1, deaths: [] }),
			'Morning. Nobody died tonight.',
			'Morgen. Heute Nacht ist niemand gestorben.'
		],
		[
			game('player_died', { player: 'p5', cause: 'executed', role: 'white_wolf' }),
			'p5 is dead (executed by the village); they were the white wolf.',
			'p5 ist tot (vom Dorf hingerichtet); Rolle: white wolf.'
		],
		[
			game('vote_cast', { player: 'p1', target: 'p2' }),
			'p1 votes against p2.',
			'p1 stimmt gegen p2.'
		],
		[
			game('game_over', { winner: 'village', winners: ['p1', 'p2'] }),
			'The village wins: p1 and p2.',
			'Das Dorf gewinnt: p1 und p2.'
		]
	])('%o', (event, en, de) => {
		expect(eventText('werewolf', event, 'en')).toBe(en);
		expect(eventText('werewolf', event, 'de')).toBe(de);
	});
});

describe('fallback', () => {
	it('has no sentence for an event it does not know', () => {
		expect(eventText('werewolf', game('brand_new_event', { player: 'p1' }), 'en')).toBeNull();
		expect(eventText('chess', game('move', {}), 'en')).toBeNull();
	});

	it('has no sentence when the data has an unexpected shape', () => {
		expect(eventText('poker', game('showdown', { hands: 'not a list' }), 'en')).toBeNull();
		expect(eventText('poker', game('pot_awarded', { shares: 5 }), 'en')).toBeNull();
	});
});

describe('matchLang', () => {
	it('is German for a German match and English otherwise', () => {
		expect(matchLang({ language: 'de' })).toBe('de');
		expect(matchLang({ language: 'en' })).toBe('en');
		expect(matchLang({})).toBe('en');
		expect(matchLang(undefined)).toBe('en');
	});
});
