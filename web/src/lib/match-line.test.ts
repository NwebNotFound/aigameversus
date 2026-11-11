import { describe, expect, it } from 'vitest';
import type { BatchSummary, MatchSummary } from './api.js';
import { batchLine, groupByBatch, matchLine, progressOf } from './match-line.js';

const ROSTER = [
	{
		id: 'glm-flash',
		name: 'glm-flash',
		model: 'z-ai/glm-5.3-flash',
		input_usd_per_mtok: 0.04,
		output_usd_per_mtok: 0.08
	}
];

function match(seats: MatchSummary['seats'], players = Object.keys(seats ?? {})): MatchSummary {
	return {
		id: 'm1',
		game: 'liars_deck',
		status: 'running',
		players,
		started_at: '2026-11-11T20:00:00Z',
		seats
	};
}

const model = (model_id: string, name = model_id) => ({ name, model_id, kind: 'model' as const });
const bot = (seat: string) => ({
	name: `Random Bot ${seat}`,
	model_id: null,
	kind: 'bot' as const
});

describe('progressOf', () => {
	it('reads the round, the hand, the night and the day from the public board', () => {
		expect(progressOf({ layout: 'card_table', round: 5 })).toBe('round 5');
		expect(progressOf({ layout: 'poker_table', hand: 3 })).toBe('hand 3');
		expect(progressOf({ layout: 'player_circle', phase: 'night', night: 2 })).toBe('night 2');
		expect(progressOf({ layout: 'player_circle', phase: 'dusk', night: 2 })).toBe('day 2');
	});

	it('says nothing before the first round or for a board it does not know', () => {
		expect(progressOf({ layout: 'card_table', round: 0 })).toBeNull();
		expect(progressOf({ layout: 'player_circle', phase: 'setup', night: 0 })).toBeNull();
		expect(progressOf({ layout: 'grid', round: 4 })).toBeNull();
		expect(progressOf(null)).toBeNull();
	});
});

describe('matchLine', () => {
	it('names model seats by model, a second seat of one model with #2, and marks it real', () => {
		const line = matchLine(
			match({
				p1: model('glm-flash'),
				p2: model('glm-flash'),
				p3: model('anthropic/claude-haiku')
			}),
			{ layout: 'card_table', round: 5 },
			12_000,
			ROSTER
		);

		expect(line.seats.map((s) => s.name)).toEqual([
			'glm-flash',
			'glm-flash #2',
			'anthropic/claude-haiku'
		]);
		expect(line.seats.every((s) => s.kind === 'model')).toBe(true);
		// The roster gives the vendor, so the colour follows the company, not the seat.
		expect(line.seats[0].colourKey).toBe('z-ai');
		expect(line).toMatchObject({ real: true, progress: 'round 5', cost_micro_eur: 12_000 });
	});

	it('calls bots Bot 1, Bot 2 and never shows a seat id', () => {
		const line = matchLine(match({ p1: bot('p1'), p2: bot('p2') }), null, 0);

		expect(line.seats.map((s) => s.name)).toEqual(['Bot 1', 'Bot 2']);
		expect(line).toMatchObject({ real: false, progress: null, cost_micro_eur: 0 });
	});

	it('keeps the row when the cost is not known', () => {
		expect(matchLine(match({ p1: bot('p1') }), null, null).cost_micro_eur).toBeNull();
	});
});

const LEAGUE = {
	id: 'E1-A2',
	label: 'E1 league A2',
	index: 14,
	of: 120,
	budget_eur: 3
};

function summary(changes: Partial<BatchSummary> = {}): BatchSummary {
	return {
		id: 'E1-A2',
		label: 'E1 league A2',
		of: 120,
		budget_eur: 3,
		matches: 18,
		statuses: { finished: 14, running: 4 },
		cost_micro_eur: 310_000,
		first_started_at: '2026-11-11T18:00:00Z',
		last_started_at: '2026-11-11T21:00:00Z',
		...changes
	};
}

describe('batchLine', () => {
	it('says how far the batch is and what it spent of its budget', () => {
		expect(batchLine(LEAGUE, summary(), 4)).toBe(
			'E1 league A2 · 14 of 120 done, 4 running · 0.3100 € of 3.00 €'
		);
	});

	it('leaves out what it does not know', () => {
		const open = { ...LEAGUE, of: null, budget_eur: null };
		expect(batchLine(open, summary({ of: null, budget_eur: null }), 4)).toBe(
			'E1 league A2 · 14 done, 4 running · 0.3100 €'
		);
		expect(batchLine(LEAGUE, summary({ cost_micro_eur: null }), 4)).toBe(
			'E1 league A2 · 14 of 120 done, 4 running'
		);
		// Without the summary only the running matches on this page are known.
		expect(batchLine(LEAGUE, null, 3)).toBe('E1 league A2 · 3 running');
	});
});

describe('groupByBatch', () => {
	it('puts the matches of one batch together where its first one was', () => {
		const items = [
			{ id: 'a', batch: LEAGUE },
			{ id: 'b', batch: null },
			{ id: 'c', batch: LEAGUE },
			{ id: 'd', batch: { ...LEAGUE, id: 'E9' } }
		];

		const entries = groupByBatch(items, (item) => item.batch);

		expect(entries.map((e) => [e.batch?.id ?? null, e.items.map((i) => i.id)])).toEqual([
			['E1-A2', ['a', 'c']],
			[null, ['b']],
			['E9', ['d']]
		]);
	});
});
