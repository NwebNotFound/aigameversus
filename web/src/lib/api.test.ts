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

	it.each([
		['an HTML page', new Response('<html>proxy error</html>', { status: 200 })],
		['a JSON object', Response.json({ detail: 'x' })],
		['an empty body', new Response('', { status: 200 })]
	])('reports a 200 with %s as unreachable', async (_, response) => {
		const { fetchFn } = fakeFetch(() => response);

		const result = await createArenaClient('http://arena:8000', fetchFn).listMatches();

		expect(result).toEqual({
			state: 'unreachable',
			reason: 'the arena sent an unexpected answer'
		});
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

const BOARD = {
	game: 'toy',
	games: ['toy'],
	rows: [
		{
			rank: 1,
			profile_id: 'a1',
			name: 'DEMO Ada',
			model_id: 'random-bot',
			rating: 1016,
			games_played: 1,
			win_rate: 1,
			average_placement: 1
		}
	]
};

describe('leaderboard', () => {
	it('asks for one game and returns the board', async () => {
		const { calls, fetchFn } = fakeFetch(() => Response.json(BOARD));

		const result = await createArenaClient('http://arena:8000', fetchFn).leaderboard('toy');

		expect(result).toEqual({ state: 'ok', data: BOARD });
		expect(calls).toEqual(['http://arena:8000/leaderboard?game=toy']);
	});

	it('asks for the overall board without a game', async () => {
		const { calls, fetchFn } = fakeFetch(() => Response.json({ ...BOARD, game: null }));

		await createArenaClient('http://arena:8000', fetchFn).leaderboard();

		expect(calls).toEqual(['http://arena:8000/leaderboard']);
	});

	it('rejects a body without rows', async () => {
		const { fetchFn } = fakeFetch(() => Response.json({ game: null }));

		const result = await createArenaClient('http://arena:8000', fetchFn).leaderboard();

		expect(result).toEqual({ state: 'unreachable', reason: 'the arena sent an unexpected answer' });
	});
});

describe('profile', () => {
	it('reports an unknown profile as not found', async () => {
		const { calls, fetchFn } = fakeFetch(() => new Response('', { status: 404 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).profile('x/y');

		expect(result).toEqual({ state: 'not_found' });
		expect(calls).toEqual(['http://arena:8000/profiles/x%2Fy']);
	});

	it('reports a refused connection as unreachable', async () => {
		const { fetchFn } = fakeFetch(() => Promise.reject(new TypeError('fetch failed')));

		const result = await createArenaClient('http://arena:8000', fetchFn).profile('a1');

		expect(result).toEqual({ state: 'unreachable', reason: 'no connection' });
	});
});
