import { describe, expect, it } from 'vitest';
import { createArenaClient, type QualificationQuote } from './api.js';
import { capEuros, parseQualifyForm, repairOf } from './qualify.js';

const QUOTE: QualificationQuote = {
	model: 'glm-flash',
	game: 'poker',
	answer_repair: 'off',
	scope: 'core',
	cases: [{ case: 'A', check: 'check or call', thought: 'required' }],
	calls: 4,
	tries_per_call: 4,
	reserved_micro_eur: 20_276,
	default_cap_micro_eur: 10_000,
	max_cap_micro_eur: 500_000,
	fits_default: false,
	config_hash: 'h'
};

function form(values: Record<string, string>) {
	const data = new FormData();
	for (const [k, v] of Object.entries(values)) data.set(k, v);
	return data;
}

const OK = { game: 'poker', answer_repair: 'off', max_eur: '0.03', confirm_spend: 'on' };

describe('parseQualifyForm', () => {
	it('sends a confirmed test whose limit holds the worst case', () => {
		expect(parseQualifyForm(form(OK), 'glm-flash', QUOTE)).toEqual({
			ok: true,
			job: {
				model: 'glm-flash',
				game: 'poker',
				answer_repair: 'off',
				confirm_spend: true,
				max_eur: 0.03
			}
		});
	});

	it.each([
		[{ ...OK, confirm_spend: undefined }, 'tick the box'],
		[{ ...OK, max_eur: '0' }, 'above 0'],
		[{ ...OK, max_eur: 'lots' }, 'above 0'],
		[{ ...OK, max_eur: '0.51' }, 'per-match cap of 0.50'],
		[{ ...OK, max_eur: '0.01' }, 'may cost up to 0.03 €'], // never shrunk to fit
		[{ ...OK, game: 'werewolf' }, 'qualification cases']
	])('refuses %o', (values, says) => {
		const clean = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== undefined));
		const parsed = parseQualifyForm(form(clean as Record<string, string>), 'glm-flash', QUOTE);

		expect(parsed.ok).toBe(false);
		expect(!parsed.ok && parsed.error).toContain(says);
	});

	it('reads the repair setting and rounds a cap up to the cent', () => {
		expect(repairOf('v1')).toBe('v1');
		expect(repairOf('bogus')).toBe('off');
		expect(capEuros(20_276)).toBe(0.03);
		expect(capEuros(10_000)).toBe(0.01);
	});
});

describe('qualification API calls', () => {
	function answering(response: Response) {
		const sent: { url: string; init?: RequestInit }[] = [];
		const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
			sent.push({ url: String(input), init });
			return response.clone();
		}) as typeof fetch;
		return { sent, arena: createArenaClient('http://arena:8000', fetchFn) };
	}

	it('asks for a free quote with the exact configuration', async () => {
		const { sent, arena } = answering(Response.json(QUOTE));

		expect(await arena.qualificationQuote('glm-flash', 'poker', 'v1')).toEqual({
			state: 'ok',
			data: QUOTE
		});
		expect(sent[0].url).toBe(
			'http://arena:8000/qualifications/quote?model=glm-flash&game=poker&answer_repair=v1'
		);
		expect(sent[0].init?.method ?? 'GET').toBe('GET');
	});

	it('treats a game without cases as not found', async () => {
		const { arena } = answering(Response.json({ detail: 'no manifest' }, { status: 422 }));

		expect(await arena.qualificationCurrent('glm-flash', 'werewolf', 'off')).toEqual({
			state: 'not_found'
		});
	});

	it('posts a start and passes on why the arena refused it', async () => {
		const job = {
			model: 'glm-flash',
			game: 'poker',
			answer_repair: 'off',
			confirm_spend: true,
			max_eur: 0.03
		} as const;
		const ok = answering(Response.json({ id: 'q1', status: 'running' }, { status: 202 }));
		const off = answering(Response.json({ detail: 'Qualification is off' }, { status: 403 }));

		expect(await ok.arena.startQualification(job)).toMatchObject({
			state: 'ok',
			data: { id: 'q1' }
		});
		expect(ok.sent[0].init?.method).toBe('POST');
		expect(JSON.parse(String(ok.sent[0].init?.body))).toEqual(job);
		expect(await off.arena.startQualification(job)).toEqual({
			state: 'refused',
			status: 403,
			detail: 'Qualification is off'
		});
	});
});
