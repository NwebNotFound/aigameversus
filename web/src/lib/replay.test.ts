import { describe, expect, it } from 'vitest';
import type { MatchEvent } from './api.js';
import { clampStep, isImportant, nextStep, shareLink, stepFromQuery } from './replay.js';

describe('clampStep', () => {
	it.each([
		[5, 10, 5],
		[-3, 10, 0],
		[12, 10, 10],
		[2.7, 10, 2],
		[Number.NaN, 10, 10]
	])('keeps %s inside a log of %s events: %s', (step, length, expected) => {
		expect(clampStep(step, length)).toBe(expected);
	});
});

describe('stepFromQuery', () => {
	it('opens a link without a step at the end of the match', () => {
		expect(stepFromQuery(null, 40)).toBe(40);
		expect(stepFromQuery('', 40)).toBe(40);
	});

	it('opens a shared step, kept inside the log', () => {
		expect(stepFromQuery('12', 40)).toBe(12);
		expect(stepFromQuery('99', 40)).toBe(40);
		expect(stepFromQuery('nonsense', 40)).toBe(40);
	});
});

describe('shareLink', () => {
	it('points to the replay at the step', () => {
		expect(shareLink('http://127.0.0.1:3100', 'm1', 7)).toBe(
			'http://127.0.0.1:3100/replays/m1?step=7'
		);
	});
});

describe('important steps', () => {
	const log = [
		{ seq: 0, source: 'engine', type: 'match_started', data: {}, visible_to: [] },
		{ seq: 1, source: 'game', type: 'deck_shuffled', data: {}, visible_to: [] },
		{ seq: 2, source: 'engine', type: 'action_accepted', data: {}, visible_to: ['p1'] },
		{
			seq: 3,
			source: 'engine',
			type: 'thought',
			data: { player: 'p1', text: 'hm' },
			visible_to: []
		},
		{ seq: 4, source: 'game', type: 'bet_action', data: { player: 'p1' }, visible_to: null },
		{ seq: 5, source: 'game', type: 'seer_inspected', data: {}, visible_to: ['p2'] },
		{ seq: 6, source: 'engine', type: 'match_finished', data: {}, visible_to: null }
	] as MatchEvent[];

	it('skips bookkeeping, and thoughts and secrets without spoilers', () => {
		expect(log.map((e) => isImportant(e, true))).toEqual([
			false,
			false,
			false,
			true,
			true,
			true,
			true
		]);
		expect(log.map((e) => isImportant(e, false))).toEqual([
			false,
			false,
			false,
			false,
			true,
			false,
			true
		]);
	});

	it('steps from one important event to the next and back', () => {
		expect(nextStep(log, 0, 1, true)).toBe(4); // step 4 ends on the thought (event 3)
		expect(nextStep(log, 4, 1, true)).toBe(5);
		expect(nextStep(log, 0, 1, false)).toBe(5); // straight to the bet
		expect(nextStep(log, 7, -1, false)).toBe(5);
		expect(nextStep(log, 5, -1, false)).toBe(0); // nothing earlier: the start
		expect(nextStep(log, 7, 1, true)).toBe(7);
	});
});
