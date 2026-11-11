/**
 * Typed client for the arena API.
 *
 * Pages call it server-side (see the `+page.server.ts` files), so the browser
 * never talks to the API directly and the API needs no CORS setup.
 */

export const DEFAULT_API_URL = 'http://127.0.0.1:8100';
const TIMEOUT_MS = 3000;

/**
 * A match as the running-matches list shows it. Provisional: `GET /matches`
 * is not on the arena yet (roadmap 1.6); this is the shape the UI expects.
 */
export interface MatchSummary {
	id: string;
	game: string;
	status: 'running' | 'paused';
	players: string[];
	round: number;
	started_at: string;
}

/** One player's standing, as in `GET /leaderboard` and `GET /profiles/{id}`. */
export interface Standing {
	profile_id: string;
	name: string;
	model_id: string;
	rating: number;
	games_played: number;
	win_rate: number | null;
	average_placement: number | null;
}

export interface LeaderboardRow extends Standing {
	rank: number;
}

export interface Leaderboard {
	/** The game shown, or null for the overall rating. */
	game: string | null;
	/** Every game with at least one rated match. */
	games: string[];
	rows: LeaderboardRow[];
}

export interface RecentMatch {
	match_id: string;
	game_id: string;
	rated_at: string;
	rank: number;
	players: number;
	rating_change: number;
}

export interface Profile {
	id: string;
	name: string;
	model_id: string;
	personality_id: string | null;
	overall: Standing | null;
	ratings: (Standing & { game_id: string })[];
	recent_matches: RecentMatch[];
	relations: { available: boolean; note: string };
	memory: { available: boolean; note: string };
}

export type Unreachable = { state: 'unreachable'; reason: string };
export type ApiResult<T> = { state: 'ok'; data: T } | { state: 'not_found' } | Unreachable;
export type MatchesResult = { state: 'ok'; matches: MatchSummary[] } | Unreachable;

export interface ArenaClient {
	health(): Promise<boolean>;
	listMatches(): Promise<MatchesResult>;
	leaderboard(game?: string): Promise<ApiResult<Leaderboard>>;
	profile(id: string): Promise<ApiResult<Profile>>;
}

export function createArenaClient(
	baseUrl: string = DEFAULT_API_URL,
	fetchFn: typeof fetch = fetch
): ArenaClient {
	const root = baseUrl.replace(/\/+$/, '');

	function get(path: string): Promise<Response> {
		return fetchFn(`${root}${path}`, {
			headers: { accept: 'application/json' },
			signal: AbortSignal.timeout(TIMEOUT_MS)
		});
	}

	/** GET a JSON body and check its shape; any failure becomes a result, never a throw. */
	async function getJson<T>(
		path: string,
		valid: (body: unknown) => boolean,
		notFound: number[] = [404]
	): Promise<ApiResult<T>> {
		let response: Response;
		try {
			response = await get(path);
		} catch (error) {
			return { state: 'unreachable', reason: describe(error) };
		}
		if (notFound.includes(response.status)) return { state: 'not_found' };
		if (!response.ok) {
			return { state: 'unreachable', reason: `the arena answered ${response.status}` };
		}
		let body: unknown;
		try {
			body = await response.json();
		} catch {
			body = undefined;
		}
		if (!valid(body)) {
			return { state: 'unreachable', reason: 'the arena sent an unexpected answer' };
		}
		return { state: 'ok', data: body as T };
	}

	return {
		async health() {
			try {
				return (await get('/health')).ok;
			} catch {
				return false;
			}
		},

		async listMatches() {
			const result = await getJson<MatchSummary[]>('/matches', Array.isArray);
			// Until the endpoint lands the arena answers 404: reachable, nothing running.
			if (result.state === 'not_found') return { state: 'ok', matches: [] };
			if (result.state === 'unreachable') return result;
			return { state: 'ok', matches: result.data };
		},

		leaderboard(game) {
			const query = game ? `?game=${encodeURIComponent(game)}` : '';
			return getJson<Leaderboard>(
				`/leaderboard${query}`,
				(body) => isObject(body) && Array.isArray(body.rows) && Array.isArray(body.games)
			);
		},

		profile(id) {
			return getJson<Profile>(
				`/profiles/${encodeURIComponent(id)}`,
				(body) => isObject(body) && typeof body.id === 'string' && Array.isArray(body.ratings),
				// 422: the id is not a valid profile id, so no such player exists either.
				[404, 422]
			);
		}
	};
}

function isObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function describe(error: unknown): string {
	if (error instanceof DOMException && error.name === 'TimeoutError') {
		return `no answer within ${TIMEOUT_MS / 1000} s`;
	}
	return 'no connection';
}
