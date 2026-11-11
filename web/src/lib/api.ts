/**
 * Typed client for the arena API.
 *
 * Pages call it server-side (see `routes/+page.server.ts`), so the browser never
 * talks to the API directly and the API needs no CORS setup.
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

export type MatchesResult =
	{ state: 'ok'; matches: MatchSummary[] } | { state: 'unreachable'; reason: string };

export interface ArenaClient {
	health(): Promise<boolean>;
	listMatches(): Promise<MatchesResult>;
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

	return {
		async health() {
			try {
				return (await get('/health')).ok;
			} catch {
				return false;
			}
		},

		async listMatches() {
			let response: Response;
			try {
				response = await get('/matches');
			} catch (error) {
				return { state: 'unreachable', reason: describe(error) };
			}
			// Until the endpoint lands the arena answers 404: reachable, nothing running.
			if (response.status === 404) return { state: 'ok', matches: [] };
			if (!response.ok) {
				return { state: 'unreachable', reason: `the arena answered ${response.status}` };
			}
			return { state: 'ok', matches: (await response.json()) as MatchSummary[] };
		}
	};
}

function describe(error: unknown): string {
	if (error instanceof DOMException && error.name === 'TimeoutError') {
		return `no answer within ${TIMEOUT_MS / 1000} s`;
	}
	return 'no connection';
}
