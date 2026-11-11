import { describe, expect, it } from 'vitest';
import type { MatchEvent, TranscriptLine } from './api.js';
import {
	beatOf,
	chapterLabel,
	commentary,
	langOf,
	linesUpTo,
	marks,
	newBeats,
	ordinal,
	resultOf,
	showdownHands,
	nextStop,
	previousStop,
	seatHue,
	seatName,
	stops,
	viewFrom,
	words
} from './viewer.js';

function event(seq: number): MatchEvent {
	return { seq, source: 'game', type: 't', data: {}, visible_to: null };
}

function line(
	seq: number | null,
	kind: TranscriptLine['kind'],
	importance: 1 | 2 | 3,
	text = `line ${seq}`,
	data: Record<string, unknown> = {}
): TranscriptLine {
	return { seq, kind, actor: 'p1', text, detail: null, importance, raw: { data } };
}

describe('viewFrom and langOf', () => {
	it('is the spectator view unless spoiler-free is asked for', () => {
		expect(viewFrom(null)).toBe('spectator');
		expect(viewFrom('nonsense')).toBe('spectator');
		expect(viewFrom('spoiler-free')).toBe('spoiler-free');
	});

	it('reads German only from the match setting', () => {
		expect(langOf({ language: 'de' })).toBe('de');
		expect(langOf({})).toBe('en');
	});
});

describe('lines on the timeline', () => {
	// A spoiler-free log skips positions 1 and 3: they were hidden.
	const events = [event(0), event(2), event(4), event(5)];
	const lines = [
		line(0, 'heading', 2, 'Round 1, table card: King'),
		line(2, 'info', 1),
		line(4, 'action', 3, 'Juniper calls LIAR'),
		line(5, 'heading', 2, 'Round 2, table card: Ace')
	];

	it('shows the lines up to an event position', () => {
		expect(linesUpTo(lines, 2).map((l) => l.seq)).toEqual([0, 2]);
		expect(linesUpTo(lines, -1)).toEqual([]);
		expect(linesUpTo(lines, null)).toHaveLength(4);
	});

	it('folds bookkeeping unless asked for it', () => {
		expect(commentary(lines, false).map((l) => l.seq)).toEqual([0, 4, 5]);
		expect(commentary(lines, true)).toHaveLength(4);
	});

	it('puts chapters and highlights at the step that shows them', () => {
		const { chapters, highlights } = marks(events, lines);
		expect(chapters.map((c) => c.step)).toEqual([1, 4]);
		expect(highlights.map((h) => h.step)).toEqual([3]);
	});

	it('stops at moments and skips bookkeeping', () => {
		const moments = stops(events, lines, 2);
		expect(moments).toEqual([1, 3, 4]);
		expect(nextStop(moments, 1, events.length)).toBe(3);
		expect(nextStop(moments, 4, events.length)).toBe(4);
		expect(previousStop(moments, 3)).toBe(1);
		expect(previousStop(moments, 1)).toBe(0);
		expect(stops(events, lines, 3)).toEqual([1, 3, 4]);
	});

	it('labels chapters short', () => {
		expect(chapterLabel(lines[0])).toBe('R1');
		expect(chapterLabel(line(1, 'heading', 2, 'Nacht 2'))).toBe('N2');
		expect(chapterLabel(line(1, 'heading', 2, 'Flop: Ah Kd 2c'))).toBeNull();
	});
});

describe('seats and words', () => {
	it('names a seat by its player, else by its id', () => {
		const players = {
			p1: { name: 'Juniper', model: 'glm-flash' },
			p2: { name: null, model: null }
		};
		expect(seatName('p1', players)).toBe('Juniper');
		expect(seatName('p2', players)).toBe('p2');
		expect(seatName('p3', undefined)).toBe('p3');
	});

	it('gives the same model the same hue', () => {
		expect(seatHue('glm-flash')).toBe(seatHue('glm-flash'));
		expect(seatHue('glm-flash') % 45).toBe(20);
	});

	it("takes a speaker's own words from the event, not the sentence", () => {
		expect(words(line(1, 'speech', 2, 'Juniper: "Hi"', { text: 'Hi' }))).toBe('Hi');
		expect(words(line(1, 'speech', 2, 'x'))).toBeNull();
	});
});

describe('beats', () => {
	const at = (seq: number, type: string, importance: 1 | 2 | 3, data = {}) =>
		({
			...line(seq, 'result', importance, `${type} ${seq}`),
			raw: { type, data }
		}) as TranscriptLine;

	it('gives a highlight its beat by event type, and nightfall one too', () => {
		expect(beatOf(at(1, 'liar_called', 3))).toBe('call');
		expect(beatOf(at(1, 'trigger_pulled', 3, { live: true }))).toBe('bang');
		expect(beatOf(at(1, 'trigger_pulled', 3, { live: false }))).toBe('click');
		expect(beatOf(at(1, 'night_started', 2))).toBe('night');
		expect(beatOf(at(1, 'something_new', 3))).toBe('highlight');
		expect(beatOf(at(1, 'cards_played', 2))).toBeNull();
	});

	it('plays the beats of what was just watched, not of a jump', () => {
		const lines = [at(1, 'cards_played', 2), at(2, 'liar_called', 3), at(3, 'trigger_pulled', 3)];
		expect(newBeats(lines, 1).map((b) => b.beat)).toEqual(['call', 'click']);
		expect(newBeats(lines, 3)).toEqual([]);
		expect(newBeats(lines, -1, 2)).toEqual([]);
	});
});

describe('results', () => {
	const end = (type: string, data: Record<string, unknown>, text: string) =>
		({ ...line(9, 'result', 3, text), raw: { type, data } }) as TranscriptLine;

	it('ranks a free-for-all, shared ranks together', () => {
		const r = resultOf(
			[
				{ player: 'p2', rank: 2 },
				{ player: 'p1', rank: 1 },
				{ player: 'p3', rank: 2 }
			],
			[end('match_over', { winner: 'p1' }, 'Match over: Juniper is the last one standing')]
		);
		expect(r).toEqual({
			kind: 'ranks',
			headline: 'Match over: Juniper is the last one standing',
			ranks: [
				{ rank: 1, seats: ['p1'] },
				{ rank: 2, seats: ['p2', 'p3'] }
			]
		});
	});

	it('names the winning side of a team game', () => {
		const r = resultOf(
			[
				{ player: 'p1', rank: 1 },
				{ player: 'p2', rank: 3 },
				{ player: 'p3', rank: 1 }
			],
			[
				end(
					'game_over',
					{ winner: 'wolves', winners: ['p1', 'p3'] },
					'Game over: the werewolves win'
				)
			]
		);
		expect(r).toMatchObject({ kind: 'team', winners: ['p1', 'p3'], others: ['p2'] });
	});

	it('has no result without placements', () => {
		expect(resultOf(null, [])).toBeNull();
	});

	it('writes ordinals', () => {
		expect([1, 2, 3, 4, 11, 12, 13, 21, 22].map(ordinal)).toEqual([
			'1st',
			'2nd',
			'3rd',
			'4th',
			'11th',
			'12th',
			'13th',
			'21st',
			'22nd'
		]);
	});

	it('turns a showdown into one row per hand, with what each won', () => {
		const lines = [
			{
				...line(5, 'reveal', 3, 'Showdown: …'),
				raw: {
					type: 'showdown',
					data: {
						hands: [
							{ player: 'p3', cards: ['6s', 'Kd'], hand: 'one_pair' },
							{ player: 'p4', cards: ['Qs', '4s'], hand: 'two_pair' }
						]
					}
				}
			},
			{
				...line(6, 'result', 3, 'Pot'),
				raw: { type: 'pot_awarded', data: { amount: 900, shares: { p4: 900 } } }
			},
			{
				...line(7, 'result', 3, 'Pot'),
				raw: { type: 'pot_awarded', data: { amount: 100, shares: { p4: 100 } } }
			},
			{ ...line(8, 'heading', 2, 'Hand 2'), raw: { type: 'hand_started', data: {} } }
		] as TranscriptLine[];
		expect(showdownHands(lines, 0)).toEqual([
			{ player: 'p3', cards: ['6s', 'Kd'], hand: 'one pair', won: 0 },
			{ player: 'p4', cards: ['Qs', '4s'], hand: 'two pair', won: 1000 }
		]);
	});
});
