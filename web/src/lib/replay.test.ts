import { describe, expect, it } from 'vitest';
import { clampStep, shareLink, stepFromQuery } from './replay.js';

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
