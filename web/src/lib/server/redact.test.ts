import { describe, expect, it } from 'vitest';
import hexFixture from '../boards/fixture-hex-map.json';
import type { LiveState, MatchEvent } from '../api.js';
import {
	publicBoard,
	publicEvents,
	publicSettings,
	publicState,
	publicTranscript
} from './redact.js';

// Board specs as the plugins' render_spec writes them (spectator data included).
const liars = {
	layout: 'card_table',
	round: 2,
	table_card: 'ace',
	turn: 'p2',
	seats: [
		{ player: 'p1', alive: true, hand: ['J1', 'Q4'], trigger_pulls: 1, chambers: 6, live: 3 },
		{ player: 'p2', alive: false, hand: [], trigger_pulls: 2, chambers: 6 }
	],
	last_play: { player: 'p1', cards: ['A4', 'A3'] }
};

const poker = {
	layout: 'poker_table',
	hand: 2,
	street: 'flop',
	board: ['Ah', 'Kd', '2c'],
	pot: 40,
	side_pots: [],
	button: 'p1',
	seats: [
		{
			player: 'p1',
			stack: 990,
			cards: ['Jh', 'Ts'],
			folded: false,
			position: 'button',
			win_probability: 0.4
		}
	]
};

const werewolf = {
	layout: 'player_circle',
	phase: 'day',
	night: 1,
	day: 1,
	turn: 'p2',
	seats: [
		{ player: 'p1', role: 'seer', alive: true },
		{ player: 'p2', role: 'werewolf', alive: false }
	]
};

describe('publicBoard', () => {
	it('turns hidden cards into as many placeholders, so the backs can be drawn', () => {
		const board = publicBoard(liars)!;
		const text = JSON.stringify(board);
		for (const secret of ['J1', 'Q4', 'A4', 'A3']) expect(text).not.toContain(secret);
		expect(board.seats).toEqual([
			{ player: 'p1', alive: true, hand: ['hidden-0', 'hidden-1'], trigger_pulls: 1, chambers: 6 },
			{ player: 'p2', alive: false, hand: [], trigger_pulls: 2, chambers: 6 }
		]);
		expect(board.last_play).toEqual({ player: 'p1', cards: ['hidden-0', 'hidden-1'] });
		expect(board.table_card).toBe('ace');
	});

	it('drops a field nobody listed as public, such as a revolver chamber', () => {
		expect(JSON.stringify(publicBoard(liars))).not.toContain('"live"');
	});

	it('keeps the community cards and drops hole cards and win chances', () => {
		const board = publicBoard(poker)!;
		expect(board.board).toEqual(['Ah', 'Kd', '2c']);
		const text = JSON.stringify(board);
		for (const secret of ['Jh', 'Ts', 'win_probability']) expect(text).not.toContain(secret);
	});

	it('sends no role, of the living or the dead', () => {
		const board = publicBoard(werewolf)!;
		expect(board.seats).toEqual([
			{ player: 'p1', role: null, alive: true },
			{ player: 'p2', role: null, alive: false }
		]);
		expect(JSON.stringify(board)).not.toMatch(/seer|werewolf/);
	});

	it('gives no board for a layout without an allowlist', () => {
		expect(publicBoard({ layout: 'unlisted_layout', tiles: [1, 2] })).toBeNull();
		expect(publicBoard({ cards: ['A1'] })).toBeNull();
		expect(publicBoard(null)).toBeNull();
	});
});

describe('publicEvents', () => {
	it('keeps only events every player saw', () => {
		const events: MatchEvent[] = [
			{ seq: 0, source: 'engine', type: 'match_started', data: { seed: 4 }, visible_to: [] },
			{ seq: 1, source: 'game', type: 'hand_dealt', data: { cards: ['K1'] }, visible_to: ['p1'] },
			{ seq: 2, source: 'game', type: 'cards_played', data: { count: 1 }, visible_to: null }
		];
		expect(publicEvents(events).map((e) => e.seq)).toEqual([2]);
	});
});

describe('publicSettings', () => {
	it('keeps a secret Werewolf role mix out, and shows a public one', () => {
		const secret = { language: 'de', template: 'classic', roles: { seer: 1 }, roles_public: false };
		expect(publicSettings(secret)).toEqual({ language: 'de', roles_public: false });
		const open = { ...secret, roles_public: true };
		expect(publicSettings(open)).toEqual(open);
	});

	it('drops a setting nobody listed as public', () => {
		expect(publicSettings({ variant: 'devil_card', secret_knob: 3 })).toEqual({
			variant: 'devil_card'
		});
	});
});

describe('publicTranscript', () => {
	it('drops a secret role mix from the opening line', () => {
		const transcript = {
			game: 'werewolf',
			lang: 'en' as const,
			spoilers: false,
			lines: [
				{
					seq: 0,
					kind: 'heading' as const,
					actor: null,
					text: 'Match started',
					detail: null,
					importance: 2 as const,
					raw: {
						type: 'match_started',
						data: { players: ['p1'], settings: { language: 'de', template: 'random_balanced' } }
					}
				}
			]
		};
		const raw = publicTranscript(transcript).lines[0].raw as { data: Record<string, unknown> };
		expect(raw.data).toEqual({ players: ['p1'], settings: { language: 'de' } });
	});
});

describe('publicState', () => {
	it('hides the seed and the secret board fields', () => {
		const state: LiveState = {
			match: {
				id: 'm',
				game: 'liars_deck',
				status: 'running',
				players: ['p1', 'p2'],
				started_at: '',
				seed: 12345,
				settings: {},
				finished_at: null,
				placements: null
			},
			board: { game: 'liars_deck', events: 9, spec: liars },
			cost: { total_micro_eur: 0, players: {} },
			control: null
		};
		const text = JSON.stringify(publicState(state));
		expect(text).not.toContain('12345');
		expect(text).not.toContain('J1');
	});
});

describe('the Throne of Tokens map, spoiler-free: one nation sees it', () => {
	type Placed = { id: string; owner: string; tile: [number, number] };
	const map = hexFixture as unknown as {
		nations: { id: string }[];
		cities: Placed[];
		armies: Placed[];
		battles: { tile: [number, number] }[];
		fog: Record<string, string[]>;
	};
	/** What `nation` sees, read from the fixture's fog independently of the code under test. */
	const seenBy = (nation: string, item: { owner?: string; tile: [number, number] }) =>
		item.owner === nation || map.fog[nation][item.tile[1]][item.tile[0]] === '1';
	const view = (nation: string | null) =>
		publicBoard(hexFixture as Record<string, unknown>, nation)!;
	const ids = (items: unknown) => (items as { id: string }[]).map((i) => i.id).sort();

	it('keeps the land, and only the cities, armies and battles the nation sees', () => {
		const board = view('p1');
		expect(board.terrain).toEqual(hexFixture.terrain);
		expect(ids(board.cities)).toEqual(ids(map.cities.filter((c) => seenBy('p1', c))));
		expect(ids(board.armies)).toEqual(ids(map.armies.filter((a) => seenBy('p1', a))));
		expect((board.battles as unknown[]).length).toBe(
			map.battles.filter((b) => seenBy('p1', b)).length
		);
		// The fixture has things p1 does not see; none of them is sent, by id or by tile.
		const hidden = [...map.cities, ...map.armies].filter((x) => !seenBy('p1', x));
		expect(hidden.length).toBeGreaterThan(0);
		const text = JSON.stringify(board);
		for (const x of hidden) {
			expect(text).not.toContain(`"id":"${x.id}"`);
			expect(text).not.toContain(`"tile":[${x.tile[0]},${x.tile[1]}]`);
		}
	});

	it('gives its own units and stock only, and its own fog row only', () => {
		const board = view('p1');
		for (const army of board.armies as { owner: string; units?: unknown }[])
			expect(army.units !== undefined).toBe(army.owner === 'p1');
		for (const nation of board.nations as { id: string; stock?: unknown }[])
			expect(nation.stock !== undefined).toBe(nation.id === 'p1');
		expect(Object.keys(board.fog as object)).toEqual(['p1']);
		expect(board.fog).toEqual({ p1: map.fog.p1 });
	});

	it('another nation sees another map; no pick, or an unknown one, is the first nation', () => {
		expect(ids(view('p2').cities)).toEqual(ids(map.cities.filter((c) => seenBy('p2', c))));
		expect(ids(view('p2').cities)).not.toEqual(ids(view('p1').cities));
		expect(view(null)).toEqual(view(map.nations[0].id));
		expect(view('p99')).toEqual(view(map.nations[0].id));
	});
});
