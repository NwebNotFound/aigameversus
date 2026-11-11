import { describe, expect, it } from 'vitest';
import { createArenaClient, type MatchSummary } from './api.js';

const MATCH: MatchSummary = {
	id: 'm1',
	game: 'poker',
	status: 'running',
	players: ['ann', 'bob'],
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
		expect(calls).toEqual(['http://arena:8000/matches?status=running']);
	});

	it('reports a server without the endpoint as unreachable', async () => {
		const { fetchFn } = fakeFetch(() => new Response('not found', { status: 404 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).listMatches();

		expect(result).toEqual({ state: 'unreachable', reason: 'the arena answered 404' });
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

	it('reports a malformed id (422) as not found', async () => {
		const { fetchFn } = fakeFetch(() => Response.json({ detail: [] }, { status: 422 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).profile('not-a-uuid');

		expect(result).toEqual({ state: 'not_found' });
	});

	it('keeps a 422 from other endpoints as unreachable', async () => {
		const { fetchFn } = fakeFetch(() => new Response('', { status: 422 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).leaderboard();

		expect(result).toEqual({ state: 'unreachable', reason: 'the arena answered 422' });
	});

	it('reports a refused connection as unreachable', async () => {
		const { fetchFn } = fakeFetch(() => Promise.reject(new TypeError('fetch failed')));

		const result = await createArenaClient('http://arena:8000', fetchFn).profile('a1');

		expect(result).toEqual({ state: 'unreachable', reason: 'no connection' });
	});
});

const RECORD = {
	...MATCH,
	seed: 7,
	settings: {},
	finished_at: null,
	placements: null
};

/** Answers like the arena for match m1: record, board, cost and, if `running`, control. */
function arena(running: boolean) {
	return (url: string) => {
		const path = new URL(url).pathname;
		if (path === '/matches/m1') return Response.json(RECORD);
		if (path === '/matches/m1/board')
			return Response.json({ game: 'poker', events: 3, spec: null });
		if (path === '/matches/m1/cost') return Response.json({ total_micro_eur: 0, players: {} });
		if (path === '/matches/m1/control') {
			return running
				? Response.json({ paused: false, turn_delay: 1 })
				: Response.json({ detail: 'not running' }, { status: 409 });
		}
		return new Response('', { status: 404 });
	};
}

describe('liveState', () => {
	it('gathers record, board, cost and control of a running match', async () => {
		const { calls, fetchFn } = fakeFetch(arena(true));

		const result = await createArenaClient('http://arena:8000', fetchFn).liveState('m1');

		expect(result).toEqual({
			state: 'ok',
			data: {
				match: RECORD,
				board: { game: 'poker', events: 3, spec: null },
				cost: { total_micro_eur: 0, players: {} },
				control: { paused: false, turn_delay: 1 }
			}
		});
		expect(calls.sort()).toEqual([
			'http://arena:8000/matches/m1',
			'http://arena:8000/matches/m1/board',
			'http://arena:8000/matches/m1/control',
			'http://arena:8000/matches/m1/cost'
		]);
	});

	it('has no control for a match that is not running', async () => {
		const { fetchFn } = fakeFetch(arena(false));

		const result = await createArenaClient('http://arena:8000', fetchFn).liveState('m1');

		expect(result).toMatchObject({ state: 'ok', data: { control: null } });
	});

	it('reports an unknown match as not found', async () => {
		const { calls, fetchFn } = fakeFetch(arena(true));

		const result = await createArenaClient('http://arena:8000', fetchFn).liveState('m2');

		expect(result).toEqual({ state: 'not_found' });
		expect(calls).toEqual(['http://arena:8000/matches/m2']);
	});

	it('reports a failing part as unreachable', async () => {
		const { fetchFn } = fakeFetch((url) =>
			url.endsWith('/cost') ? new Response('boom', { status: 500 }) : arena(true)(url)
		);

		const result = await createArenaClient('http://arena:8000', fetchFn).liveState('m1');

		expect(result).toEqual({ state: 'unreachable', reason: 'the arena answered 500' });
	});
});

describe('control', () => {
	function recording() {
		const requests: { url: string; method: string; body: unknown }[] = [];
		const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
			requests.push({
				url: String(input),
				method: init?.method ?? 'GET',
				body: init?.body ? JSON.parse(String(init.body)) : null
			});
			return Response.json({ paused: true, turn_delay: 1 });
		}) as typeof fetch;
		return { requests, fetchFn };
	}

	it('posts pause, resume and abort', async () => {
		const { requests, fetchFn } = recording();
		const client = createArenaClient('http://arena:8000', fetchFn);

		for (const action of ['pause', 'resume', 'abort'] as const)
			await client.control('m1', { action });

		expect(requests).toEqual(
			['pause', 'resume', 'abort'].map((action) => ({
				url: `http://arena:8000/matches/m1/${action}`,
				method: 'POST',
				body: null
			}))
		);
	});

	it('puts a new speed', async () => {
		const { requests, fetchFn } = recording();

		const result = await createArenaClient('http://arena:8000', fetchFn).control('m1', {
			action: 'speed',
			turn_delay: 0.25
		});

		expect(requests).toEqual([
			{ url: 'http://arena:8000/matches/m1/speed', method: 'PUT', body: { turn_delay: 0.25 } }
		]);
		expect(result).toEqual({ state: 'ok', data: { paused: true, turn_delay: 1 } });
	});

	it('reports a match that is not running as not found', async () => {
		const { fetchFn } = fakeFetch(() => Response.json({ detail: 'x' }, { status: 409 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).control('m1', {
			action: 'pause'
		});

		expect(result).toEqual({ state: 'not_found' });
	});
});

describe('eventsUrl', () => {
	it('is the WebSocket of the match on the arena', () => {
		expect(createArenaClient('http://arena:8000/').eventsUrl('m1')).toBe(
			'ws://arena:8000/matches/m1/events'
		);
		expect(createArenaClient('https://arena.example').eventsUrl('a/b')).toBe(
			'wss://arena.example/matches/a%2Fb/events'
		);
	});
});

describe('startMatch', () => {
	const BODY = { game: 'toy', players: 2, settings: {}, turn_delay: 1 };

	function answering(response: Response) {
		const sent: { url: string; init?: RequestInit }[] = [];
		const fetchFn = (async (input: RequestInfo | URL, init?: RequestInit) => {
			sent.push({ url: String(input), init });
			return response;
		}) as typeof fetch;
		return { sent, fetchFn };
	}

	it('posts the match and returns its record', async () => {
		const { sent, fetchFn } = answering(Response.json(RECORD, { status: 201 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).startMatch(BODY);

		expect(result).toEqual({ state: 'ok', data: RECORD });
		expect(sent[0].url).toBe('http://arena:8000/matches');
		expect(sent[0].init?.method).toBe('POST');
		expect(JSON.parse(String(sent[0].init?.body))).toEqual(BODY);
	});

	it('passes on why the game refused', async () => {
		const { fetchFn } = answering(
			Response.json({ detail: 'High Card takes 2 to 4 players' }, { status: 422 })
		);

		const result = await createArenaClient('http://arena:8000', fetchFn).startMatch(BODY);

		expect(result).toEqual({
			state: 'refused',
			status: 422,
			detail: 'High Card takes 2 to 4 players'
		});
	});

	it('joins the messages of a field error list', async () => {
		const detail = [{ msg: 'Input should be >= 0' }, { msg: 'Field required' }];
		const { fetchFn } = answering(Response.json({ detail }, { status: 422 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).startMatch(BODY);

		expect(result).toMatchObject({ detail: 'Input should be >= 0; Field required' });
	});

	it('reports a full arena as refused', async () => {
		const { fetchFn } = answering(
			Response.json({ detail: '10 matches are running' }, { status: 429 })
		);

		const result = await createArenaClient('http://arena:8000', fetchFn).startMatch(BODY);

		expect(result).toEqual({ state: 'refused', status: 429, detail: '10 matches are running' });
	});

	it('reports a server error as unreachable', async () => {
		const { fetchFn } = answering(new Response('boom', { status: 500 }));

		const result = await createArenaClient('http://arena:8000', fetchFn).startMatch(BODY);

		expect(result).toEqual({ state: 'unreachable', reason: 'the arena answered 500' });
	});
});

describe('setup', () => {
	it('returns the options of the new-match form', async () => {
		const options = {
			model_seats: false,
			models: [{ id: 'm', model: 'x/m' }],
			personalities: [],
			caps: { match_eur: 0.5, month_eur: 5 }
		};
		const { calls, fetchFn } = fakeFetch(() => Response.json(options));

		const result = await createArenaClient('http://arena:8000', fetchFn).setup();

		expect(result).toEqual({ state: 'ok', data: options });
		expect(calls).toEqual(['http://arena:8000/setup']);
	});
});
