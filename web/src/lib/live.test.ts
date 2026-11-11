import { describe, expect, it } from 'vitest';
import type { MatchEvent } from './api.js';
import { columnOf, describe as describeEvent, euros, hidden, merge, playersOf } from './live.js';

function event(
	seq: number,
	type: string,
	data = {},
	visible_to: string[] | null = null
): MatchEvent {
	return { seq, source: 'game', type, data, visible_to };
}

describe('columnOf', () => {
	it('puts public events in the middle and everything else behind the scenes', () => {
		expect(columnOf(event(0, 'cards_played'))).toBe('public');
		expect(columnOf(event(1, 'hand_dealt', {}, ['p1']))).toBe('behind');
		expect(columnOf(event(2, 'thought', {}, []))).toBe('behind');
	});
});

describe('playersOf', () => {
	it('is the author, the subject and who may see it', () => {
		const vote = event(0, 'wolf_vote', { player: 'p3', target: 'p6' }, ['p3', 'p5']);

		expect(playersOf(vote).sort()).toEqual(['p3', 'p5', 'p6']);
	});

	it('is nobody for a spectator-only event about no player', () => {
		expect(playersOf(event(0, 'match_started', { seed: 1 }, []))).toEqual([]);
	});
});

describe('describe', () => {
	it('shows a message as the words of its author', () => {
		expect(describeEvent(event(0, 'message', { player: 'p2', text: 'Not me.' }))).toEqual({
			kind: 'message',
			player: 'p2',
			text: 'Not me.'
		});
	});

	it('shows a thought as the private text of its player', () => {
		const thought = event(0, 'thought', { player: 'p1', text: 'p2 is bluffing' }, []);

		expect(describeEvent(thought)).toEqual({
			kind: 'thought',
			player: 'p1',
			text: 'p2 is bluffing'
		});
	});

	it('shows a narration as its text', () => {
		const night = event(0, 'narration', { key: 'night_falls', text: 'Night 1 falls.' });

		expect(describeEvent(night)).toEqual({ kind: 'narration', text: 'Night 1 falls.' });
	});

	it('shows any other event as its type and data', () => {
		const call = event(0, 'liar_called', { caller: 'p2', target: 'p1', automatic: false });

		expect(describeEvent(call)).toEqual({
			kind: 'event',
			player: null,
			title: 'liar called',
			details: 'caller: p2 · target: p1 · automatic: false'
		});
	});

	it('names the player of an event and lists its values', () => {
		const dealt = event(0, 'hand_dealt', { player: 'p1', cards: ['Q3', 'K3'] }, ['p1']);

		expect(describeEvent(dealt)).toMatchObject({ player: 'p1', details: 'cards: Q3, K3' });
	});

	it('keeps text that looks like HTML as text', () => {
		const sneaky = event(0, 'message', { player: 'p2', text: '<img src=x onerror=alert(1)>' });

		expect(describeEvent(sneaky)).toMatchObject({ text: '<img src=x onerror=alert(1)>' });
	});
});

describe('merge', () => {
	it('keeps every position once and in order, also when a reconnect sends events again', () => {
		const first = [event(0, 'a'), event(1, 'b')];
		const again = [event(1, 'b-again'), event(2, 'c'), event(0, 'a-again')];

		const log = merge(first, again);

		expect(log.map((e) => [e.seq, e.type])).toEqual([
			[0, 'a'],
			[1, 'b'],
			[2, 'c']
		]);
	});
});

describe('hidden', () => {
	it('hides hands, hole cards, roles and win chances only with spoilers off', () => {
		for (const field of ['hand', 'cards', 'role', 'win_probability']) {
			expect(hidden(field, false)).toBe(true);
			expect(hidden(field, true)).toBe(false);
		}
		expect(hidden('stack', false)).toBe(false);
	});
});

describe('euros', () => {
	it('shows millionths of a euro with four decimals, rounded up', () => {
		expect(euros(0)).toBe('0.0000 €');
		expect(euros(350)).toBe('0.0004 €');
		expect(euros(1_234_567)).toBe('1.2346 €');
		expect(euros(1)).toBe('0.0001 €');
		expect(euros(500_000)).toBe('0.5000 €');
	});
});
