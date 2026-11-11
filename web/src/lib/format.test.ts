import { describe, expect, it } from 'vitest';
import { statLabel, statValue } from './format.js';

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
