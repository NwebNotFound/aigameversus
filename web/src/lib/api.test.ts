import { describe, expect, it } from 'vitest';
import { createArenaClient, type MatchSummary } from './api.js';

const MATCH: MatchSummary = {
	id: 'm1',
	game: 'poker',
	status: 'running',
	players: ['ann', 'bob'],
	round: 3,
	started_at: '2026-11-11T02:00:00Z'
};

/** A fake fetch that records the URL and answers with `respond`. */
function fakeFetch(respond: (url: string) => Response | Promise<Response>) {
	const calls: string[] = [];
	const fetchFn = (async (input: RequestInfo | URL) => {
		calls.push(String(input));
		return respond(String(input));
	}) as typeof fetch;
	return { calls, fetchFn };
}

describe('listMatches', () => {
	it('returns the matches the arena lists', async () => {
		const { calls, fetchFn } = fakeFetch(() => Response.json([MATCH]));

		const result = await createArenaClient('http://arena:8000/', fetchFn).listMatches();

		expect(result).toEqual({ state: 'ok', matches: [MATCH] });
		expect(calls).toEqual(['http://arena:8000/matches']);
	});

	it('treats a missing endpoint as no running matches', async () => {
		const { fetchFn } = fakeFetch(() => new Response('not found', { status: 404 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).listMatches();

		expect(result).toEqual({ state: 'ok', matches: [] });
	});

	it('reports a refused connection as unreachable', async () => {
		const { fetchFn } = fakeFetch(() => Promise.reject(new TypeError('fetch failed')));

		const result = await createArenaClient('http://arena:8000', fetchFn).listMatches();

		expect(result).toEqual({ state: 'unreachable', reason: 'no connection' });
	});

	it('reports a timeout as unreachable', async () => {
		const timeout = new DOMException('timed out', 'TimeoutError');
		const { fetchFn } = fakeFetch(() => Promise.reject(timeout));

		const result = await createArenaClient('http://arena:8000', fetchFn).listMatches();

		expect(result).toEqual({ state: 'unreachable', reason: 'no answer within 3 s' });
	});

	it('reports a server error as unreachable with the status', async () => {
		const { fetchFn } = fakeFetch(() => new Response('boom', { status: 500 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).listMatches();

		expect(result).toEqual({ state: 'unreachable', reason: 'the arena answered 500' });
	});
});

describe('health', () => {
	it('is true when /health answers 200', async () => {
		const { calls, fetchFn } = fakeFetch(() => Response.json({ status: 'ok' }));

		expect(await createArenaClient('http://arena:8000', fetchFn).health()).toBe(true);
		expect(calls).toEqual(['http://arena:8000/health']);
	});

	it('is false when the arena cannot be reached', async () => {
		const { fetchFn } = fakeFetch(() => Promise.reject(new TypeError('fetch failed')));

		expect(await createArenaClient('http://arena:8000', fetchFn).health()).toBe(false);
	});
});
