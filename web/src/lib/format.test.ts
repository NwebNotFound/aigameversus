import { describe, expect, it } from 'vitest';
import { statLabel, statValue, footerLine } from './format.js';

describe('statValue', () => {
	it.each([
		['lie_rate', 0.375, '38 %'],
		['caught_share', 1, '100 %'],
		['plays', 12, '12'],
		['rounds_survived_per_match', 2.3333, '2.33'],
		['boldest_bluff_risk', null, '–'],
		['eliminated', true, 'yes'],
		['favourite_role', 'seer', 'seer']
	])('shows %s = %s as %s', (field, value, shown) => {
		expect(statValue(field, value)).toBe(shown);
	});
});

describe('statLabel', () => {
	it('turns a field name into a label', () => {
		expect(statLabel('call_success_rate')).toBe('Call success rate');
	});
});

describe('footerLine', () => {
	it('says what the server plays with, and the month when the ledger answers', () => {
		expect(footerLine(null, null)).toBe('AI models play, humans watch.');
		expect(footerLine(false, null)).toBe(
			'AI models play, humans watch. Bots only: real models are off on this server.'
		);
		expect(footerLine(true, null)).toBe('AI models play, humans watch. Real models enabled.');
		expect(footerLine(true, { spent_micro_eur: 301_000, cap_micro_eur: 25_000_000 })).toBe(
			'AI models play, humans watch. Real models enabled · EUR 0.30 of 25.00 this month.'
		);
	});
});
