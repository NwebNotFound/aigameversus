import { describe, expect, it } from 'vitest';
import type { ReplaySummary } from './api.js';
import { filterReplays } from './replay-list.js';

function replay(id: string, game: string, finished: string, real: boolean): ReplaySummary {
	return {
		id,
		game,
		players: ['p1', 'p2'],
		winners: ['p1'],
		started_at: '2026-11-11T08:00:00Z',
		finished_at: finished,
		cost_micro_eur: 0,
		seats: real ? { p1: { name: 'Gemini', model_id: 'gemini-flash', kind: 'model' } } : null
	};
}

const LIST = [
	replay('old-bots', 'poker', '2026-11-11T10:05:00Z', false),
	replay('new-bots', 'poker', '2026-11-11T12:00:00Z', false),
	replay('old-real', 'werewolf', '2026-11-11T09:00:00Z', true),
	replay('new-real', 'poker', '2026-11-11T11:00:00Z', true)
];

describe('filterReplays', () => {
	it('pins real-model matches first, then newest first', () => {
		expect(filterReplays(LIST, '', '').map((r) => r.id)).toEqual([
			'new-real',
			'old-real',
			'new-bots',
			'old-bots'
		]);
	});

	it('filters by game and by kind', () => {
		expect(filterReplays(LIST, 'poker', '').map((r) => r.id)).toEqual([
			'new-real',
			'new-bots',
			'old-bots'
		]);
		expect(filterReplays(LIST, '', 'real').map((r) => r.id)).toEqual(['new-real', 'old-real']);
		expect(filterReplays(LIST, 'poker', 'bots').map((r) => r.id)).toEqual(['new-bots', 'old-bots']);
	});
});
