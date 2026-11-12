import { describe, expect, it } from 'vitest';
import type { MatchEvent, TranscriptLine } from './api.js';
import {
	beatOf,
	chapterLabel,
	commentary,
	langOf,
	attempts,
	mentionParts,
	mergeSeats,
	namedText,
	withDisplayNames,
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

describe('mergeSeats', () => {
	const roster = [
		{
			id: 'gemini-flash-lite',
			model: 'google/gemini-2.5-flash-lite',
			name: 'Gemini Flash Lite',
			input_usd_per_mtok: 0.1,
			output_usd_per_mtok: 0.4
		}
	];

	it('takes a running model match from the record, though the transcript knows nothing', () => {
		const seats = mergeSeats(
			['p1', 'p2'],
			{
				p1: { name: 'gemini-flash-lite', model_id: 'gemini-flash-lite', kind: 'model' },
				p2: { name: 'Random Bot p2', model_id: null, kind: 'bot' }
			},
			{ p1: { name: null, model: null }, p2: { name: null, model: null } },
			roster
		);
		expect(seats.p1).toEqual({
			display: 'gemini-flash-lite',
			name: 'gemini-flash-lite',
			model: 'gemini-flash-lite',
			kind: 'model',
			vendor: 'google',
			personality: null,
			price: { input: 0.1, output: 0.4 }
		});
		expect(seats.p2).toMatchObject({ name: 'Random Bot p2', model: null, kind: 'bot' });
	});

	it("prefers the transcript's player name (a profile name) over the record's", () => {
		const seats = mergeSeats(
			['p1'],
			{ p1: { name: 'glm-flash', model_id: 'glm-flash', kind: 'model' } },
			{ p1: { name: 'Juniper', model: 'glm-flash' } }
		);
		expect(seats.p1).toMatchObject({
			name: 'Juniper',
			model: 'glm-flash',
			kind: 'model',
			vendor: null
		});
	});

	it('keeps an old match without seats as it was', () => {
		expect(mergeSeats(['p1'], undefined, undefined).p1).toMatchObject({
			name: null,
			kind: undefined
		});
	});
});

describe('display names', () => {
	it('names like the arena: every repeat numbered, bots by seat number', () => {
		const seats = withDisplayNames(['p1', 'p2', 'p3', 'p4'], {
			p1: { name: 'gpt-luna', model: 'gpt-luna', kind: 'model' },
			p2: { name: 'Random Bot p2', model: null, kind: 'bot' },
			p3: { name: 'gpt-luna', model: 'gpt-luna', kind: 'model' },
			p4: { name: 'Random Bot p4', model: null, kind: 'bot' }
		});
		expect(['p1', 'p2', 'p3', 'p4'].map((s) => seatName(s, seats))).toEqual([
			'gpt-luna #1',
			'Bot 2',
			'gpt-luna #2',
			'Bot 4'
		]);
	});

	it('keeps a display name the API gave, and a profile name over the model id', () => {
		const seats = withDisplayNames(['p1', 'p2'], {
			p1: { name: 'Juniper', model: 'glm-flash', kind: 'model' },
			p2: { name: 'x', model: 'x', kind: 'model', display: 'Server name' }
		});
		expect(seatName('p1', seats)).toBe('Juniper');
		expect(seatName('p2', seats)).toBe('Server name');
	});

	it('replaces seat ids in transcript text, also inside the old bot label', () => {
		const seats = withDisplayNames(['p1', 'p2'], {
			p1: { name: 'gpt-luna', model: 'gpt-luna', kind: 'model' },
			p2: { name: 'Random Bot p2', model: null, kind: 'bot' }
		});
		expect(namedText('p1 calls LIAR on Random Bot p2 (random-bot)', seats)).toBe(
			'gpt-luna calls LIAR on Bot 2'
		);
		expect(namedText('Ergebnis: 1. p2  2. p1', seats)).toBe('Ergebnis: 1. Bot 2  2. gpt-luna');
		expect(namedText('top10 and p9 stay', seats)).toBe('top10 and p9 stay');
	});
});

describe('mentionParts', () => {
	const seats = withDisplayNames(['p1', 'p2', 'p3', 'p4'], {
		p1: { name: 'mistral-small', model: 'mistral-small', kind: 'model' },
		p2: { name: 'gpt-luna', model: 'gpt-luna', kind: 'model' },
		p3: { name: 'qwen-flash', model: 'qwen-flash', kind: 'model' },
		p4: { name: 'gemini-flash-lite', model: 'gemini-flash-lite', kind: 'model' }
	});

	it("turns the seat a model named into a mention (Nils' sentence)", () => {
		expect(mentionParts('p2, two kings with your history? I doubt it!', seats)).toEqual([
			{ seat: 'p2', text: 'p2' },
			{ text: ', two kings with your history? I doubt it!' }
		]);
	});

	it('leaves a seat that is not in the match, and words that only contain p2, as text', () => {
		expect(mentionParts('p9 and top2 and mp3', seats)).toEqual([{ text: 'p9 and top2 and mp3' }]);
	});

	it('finds several mentions, in any case', () => {
		const parts = mentionParts('P3 bluffs; p4 called p3.', seats);
		expect(parts.filter((p) => 'seat' in p).map((p) => (p as { seat: string }).seat)).toEqual([
			'p3',
			'p4',
			'p3'
		]);
		expect(parts.map((p) => p.text).join('')).toBe('P3 bluffs; p4 called p3.');
	});
});

describe('mentions with what a language glues to them', () => {
	const seats = withDisplayNames(['p1', 'p2', 'p3', 'p4'], {
		p1: { name: 'gpt-luna', model: 'gpt-luna', kind: 'model' },
		p2: { name: 'mistral-small', model: 'mistral-small', kind: 'model' },
		p3: { name: 'deepseek-flash', model: 'deepseek-flash', kind: 'model' },
		p4: { name: 'gemini-flash-lite', model: 'gemini-flash-lite', kind: 'model' }
	});
	const seatsOf = (text: string) =>
		mentionParts(text, seats).flatMap((p) => ('seat' in p ? [p.seat] : []));

	it('takes "Auf p4s Frage" as p4, with the "s" left as text', () => {
		expect(mentionParts('Auf p4s Frage: …', seats)).toEqual([
			{ text: 'Auf ' },
			{ seat: 'p4', text: 'p4' },
			{ text: 's Frage: …' }
		]);
	});

	it("takes p3's vote, p4’s, p4-Antwort and p4: as mentions", () => {
		expect(seatsOf("p3's vote")).toEqual(['p3']);
		expect(seatsOf('p4’s turn, p4-Antwort, p4: yes')).toEqual(['p4', 'p4', 'p4']);
	});

	it('reads upper case and lists', () => {
		expect(seatsOf('P4 lügt; p1/p2/p3 stimmen')).toEqual(['p4', 'p1', 'p2', 'p3']);
	});

	it('leaves seats not in the match, ids inside words and longer numbers alone', () => {
		expect(seatsOf('p9, mp3, top2, p41')).toEqual([]);
	});

	it('names plain text by the same rule', () => {
		expect(namedText('Auf p4s Frage', seats)).toBe('Auf gemini-flash-lites Frage');
		expect(namedText('P2 calls p9', seats)).toBe('mistral-small calls p9');
	});
});

describe('attempts', () => {
	const at = (kind: TranscriptLine['kind'], type: string, actor = 'p2'): TranscriptLine => ({
		seq: 0,
		kind,
		actor,
		text: type,
		detail: null,
		importance: kind === 'info' ? 2 : 2,
		raw: { type }
	});

	it("folds a refused attempt's thought and marks the move that counted", () => {
		// The shape of gpt-luna's flop check in Nils' Poker match: two refusals, then a check.
		const lines = [
			at('thought', 'thought'),
			at('info', 'action_rejected'),
			at('thought', 'thought'),
			at('info', 'action_rejected'),
			at('thought', 'thought'),
			at('info', 'action_accepted'),
			at('action', 'bet_action'),
			at('thought', 'thought', 'p1'),
			at('action', 'bet_action', 'p1')
		];
		const { hidden, marks } = attempts(lines);
		expect([...hidden]).toEqual([lines[0], lines[2]]);
		expect(marks.get(lines[6])).toEqual({ retries: 2, fallback: false });
		expect(marks.has(lines[8])).toBe(false);
	});

	it('marks a random fallback', () => {
		const lines = [
			at('info', 'action_rejected'),
			at('info', 'action_fallback'),
			at('action', 'bet_action'),
			at('info', 'agent_failed', 'p1'),
			at('action', 'bet_action', 'p1')
		];
		const { marks } = attempts(lines);
		expect(marks.get(lines[2])).toEqual({ retries: 1, fallback: true });
		expect(marks.get(lines[4])).toEqual({ retries: 0, fallback: true });
	});
});
