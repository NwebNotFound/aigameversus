/**
 * Typed client for the arena API.
 *
 * Pages call it server-side (see the `+page.server.ts` files), so the browser
 * never talks to the API directly and the API needs no CORS setup.
 */

export const DEFAULT_API_URL = 'http://127.0.0.1:8100';
const TIMEOUT_MS = 3000;

export type MatchStatus = 'running' | 'finished' | 'failed' | 'interrupted' | 'aborted';

/** A match as `GET /matches` lists it. */
export interface MatchSummary {
	id: string;
	game: string;
	status: MatchStatus;
	players: string[];
	started_at: string;
}

/** A match as `GET /matches/{id}` returns it. */
export interface MatchRecord extends MatchSummary {
	seed: number;
	settings: Record<string, unknown>;
	finished_at: string | null;
	placements: { player: string; rank: number }[] | null;
}

/** One event of a match log, as the event stream sends it. */
export interface MatchEvent {
	seq: number;
	source: 'engine' | 'game';
	type: string;
	data: Record<string, unknown>;
	/** null: public; a list: only these players; empty: spectators only. */
	visible_to: string[] | null;
}

/** `GET /matches/{id}/control`: how a running match is played right now. */
export interface Control {
	paused: boolean;
	turn_delay: number;
}

/** `GET /matches/{id}/board`: the game's render_spec after the stored turns. */
export interface Board {
	game: string;
	events: number;
	spec: Record<string, unknown> | null;
}

/** `GET /matches/{id}/cost`, in millionths of a euro. */
export interface Cost {
	total_micro_eur: number;
	players: Record<string, number>;
}

/** Everything the live view shows next to the event log. */
export interface LiveState {
	match: MatchRecord;
	board: Board;
	cost: Cost;
	/** null when the match is not running (any more). */
	control: Control | null;
}

export type ControlAction =
	| { action: 'pause' }
	| { action: 'resume' }
	| { action: 'abort' }
	| { action: 'speed'; turn_delay: number };

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

/** `GET /profiles/{id}/stats`: totals per game, from the logs of the rated matches. */
export interface ProfileStats {
	profile_id: string;
	games: { game_id: string; matches: number; stats: Record<string, unknown> | null }[];
}

export type Unreachable = { state: 'unreachable'; reason: string };
export type ApiResult<T> = { state: 'ok'; data: T } | { state: 'not_found' } | Unreachable;
export type MatchesResult = { state: 'ok'; matches: MatchSummary[] } | Unreachable;

export interface ArenaClient {
	health(): Promise<boolean>;
	listMatches(): Promise<MatchesResult>;
	leaderboard(game?: string): Promise<ApiResult<Leaderboard>>;
	profile(id: string): Promise<ApiResult<Profile>>;
	profileStats(id: string): Promise<ApiResult<ProfileStats>>;
	liveState(id: string): Promise<ApiResult<LiveState>>;
	/** Pause, resume, abort or re-time a running match; `not_found` when it is not running. */
	control(id: string, command: ControlAction): Promise<ApiResult<Control | MatchRecord>>;
	/** The WebSocket URL of a match's event stream. */
	eventsUrl(id: string): string;
}

export function createArenaClient(
	baseUrl: string = DEFAULT_API_URL,
	fetchFn: typeof fetch = fetch
): ArenaClient {
	const root = baseUrl.replace(/\/+$/, '');

	function get(path: string, init: RequestInit = {}): Promise<Response> {
		return fetchFn(`${root}${path}`, {
			...init,
			headers: { accept: 'application/json', ...init.headers },
			signal: AbortSignal.timeout(TIMEOUT_MS)
		});
	}

	/** GET a JSON body and check its shape; any failure becomes a result, never a throw. */
	async function getJson<T>(
		path: string,
		valid: (body: unknown) => boolean,
		notFound: number[] = [404],
		init: RequestInit = {}
	): Promise<ApiResult<T>> {
		let response: Response;
		try {
			response = await get(path, init);
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
			const result = await getJson<MatchSummary[]>('/matches?status=running', Array.isArray, []);
			if (result.state !== 'ok') return result as Unreachable;
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
		},

		profileStats(id) {
			return getJson<ProfileStats>(
				`/profiles/${encodeURIComponent(id)}/stats`,
				(body) => isObject(body) && Array.isArray(body.games),
				[404, 422]
			);
		},

		async liveState(id) {
			const match = encodeURIComponent(id);
			// 422: not a valid match id, so no such match either.
			const record = await getJson<MatchRecord>(`/matches/${match}`, isObject, [404, 422]);
			if (record.state !== 'ok') return record;
			const [board, cost, control] = await Promise.all([
				getJson<Board>(`/matches/${match}/board`, (body) => isObject(body) && 'spec' in body),
				getJson<Cost>(`/matches/${match}/cost`, (body) => isObject(body) && isObject(body.players)),
				// 409: the match is not running, so there is nothing to control.
				getJson<Control>(`/matches/${match}/control`, isObject, [409])
			]);
			if (board.state !== 'ok') return board;
			if (cost.state !== 'ok') return cost;
			if (control.state === 'unreachable') return control;
			return {
				state: 'ok',
				data: {
					match: record.data,
					board: board.data,
					cost: cost.data,
					control: control.state === 'ok' ? control.data : null
				}
			};
		},

		control(id, command) {
			const match = encodeURIComponent(id);
			const speed = command.action === 'speed';
			return getJson<Control | MatchRecord>(
				`/matches/${match}/${command.action}`,
				isObject,
				[404, 409, 422],
				speed
					? {
							method: 'PUT',
							headers: { 'content-type': 'application/json' },
							body: JSON.stringify({ turn_delay: command.turn_delay })
						}
					: { method: 'POST' }
			);
		},

		eventsUrl(id) {
			return `${root.replace(/^http/, 'ws')}/matches/${encodeURIComponent(id)}/events`;
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
