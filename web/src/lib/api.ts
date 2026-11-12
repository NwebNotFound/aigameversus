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
	/** Who sits where: set for every match since model seats (D-082). */
	seats?: Record<string, RecordSeat>;
	/** The batch it was played in (a league, an experiment stage); null or missing: none. */
	batch?: MatchBatch | null;
}

/** A match's batch, as `POST /matches` took it. */
export interface MatchBatch {
	id: string;
	label: string;
	index: number | null;
	of: number | null;
	budget_eur: number | null;
}

/** `GET /batches/{id}`: how far a batch is and what it cost. */
export interface BatchSummary {
	id: string;
	label: string;
	of: number | null;
	budget_eur: number | null;
	matches: number;
	statuses: Partial<Record<MatchStatus, number>>;
	/** null while the ledger cannot be read. */
	cost_micro_eur: number | null;
	first_started_at: string;
	last_started_at: string;
}

/** A match as `GET /matches/{id}` returns it. */
export interface MatchRecord extends MatchSummary {
	/** null on a spoiler-free page: the seed gives every hidden draw away. */
	seed: number | null;
	settings: Record<string, unknown>;
	finished_at: string | null;
	placements: { player: string; rank: number }[] | null;
	origin?: 'played' | 'imported';
}

/** A seat as the match record stores it. */
export interface RecordSeat {
	name: string;
	model_id: string | null;
	kind: 'model' | 'bot';
	personality?: string | null;
	display?: string | null;
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

/** A finished match as `GET /replays` lists it. */
export interface ReplaySummary {
	id: string;
	game: string;
	players: string[];
	winners: string[];
	started_at: string;
	finished_at: string;
	cost_micro_eur: number;
	seats?: Record<string, RecordSeat>;
	real?: boolean;
}

/** `GET /matches/{id}/cost`, in millionths of a euro. */
export interface Cost {
	total_micro_eur: number;
	players: Record<string, number>;
}

/** What a transcript line is, for drawing it (arena/transcript/common.py). */
export type LineKind =
	| 'heading'
	| 'action'
	| 'speech'
	| 'whisper'
	| 'thought'
	| 'reveal'
	| 'result'
	| 'narration'
	| 'info';

/** One readable line of `GET /matches/{id}/transcript`: the only text the UI shows for an event. */
export interface TranscriptLine {
	/** The position of the event the line tells, or null for a line of its own. */
	seq: number | null;
	kind: LineKind;
	/** The seat id of whoever acts or speaks. */
	actor: string | null;
	text: string;
	detail: string | null;
	/** 1 bookkeeping, 2 normal, 3 highlight. */
	importance: 1 | 2 | 3;
	raw: Record<string, unknown>;
	/**
	 * Spoiler-free only, added by the web server: the move was repaired (tier 1, the call
	 * read as meant; tier 2, mapped to a legal move by Jev with probability `p`). The
	 * spectator view reads the same from the bookkeeping lines; nothing else is passed on.
	 */
	repair?: { tier: 1 | 2; p: number | null } | null;
}

/** Who sits in a seat; name and model null for seats nobody named. */
export interface Seat {
	name: string | null;
	model: string | null;
	/** The name people read: "gpt-luna", "gpt-luna #2", "Bot 1"; never the seat id. */
	display?: string | null;
	/** Filled in by the web from the match record and the model roster. */
	kind?: 'model' | 'bot';
	/** The provider's company, e.g. "google" from "google/gemini-2.5-flash-lite". */
	vendor?: string | null;
	personality?: string | null;
	/** US dollars per million tokens, from config/models.yaml. */
	price?: { input: number; output: number } | null;
}

export interface Transcript {
	game: string;
	lang: 'en' | 'de';
	spoilers: boolean;
	lines: TranscriptLine[];
	/** seat -> name and model, in seat order; missing on arenas that do not send it yet. */
	players?: Record<string, Seat>;
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

/** A game as `GET /games` lists it. */
export interface GameInfo {
	id: string;
	name: string;
	min_players: number;
	max_players: number;
}

/** `GET /setup`: what the new-match form offers. */
export interface SetupOptions {
	/** Whether a seat can be a model yet; until then every seat is a random bot. */
	model_seats: boolean;
	/** Whether a table may mix models and random bots (`seats` in POST /matches). */
	mixed_seats?: boolean;
	/** Whether a model seat in `seats` may name a personality. */
	seat_personalities?: boolean;
	models: {
		id: string;
		model: string;
		name: string;
		input_usd_per_mtok: number;
		output_usd_per_mtok: number;
	}[];
	personalities: { id: string; name: string; description: string }[];
	caps: { match_eur: number; month_eur: number };
}

/** A Werewolf role, as `GET /games/werewolf/roles` lists it. */
export interface WerewolfRole {
	id: string;
	name: string;
	team: 'village' | 'wolves' | 'solo';
	unique: boolean;
	weight: number;
	description: string;
}

export interface Balance {
	total: number;
	verdict: 'village' | 'even' | 'wolves';
}

/** `GET /games/werewolf/templates?players=N`. */
export interface WerewolfTemplate {
	id: string;
	name: string;
	min_players: number;
	random: boolean;
	/** The roles at this table; null for a random template or one that does not fit. */
	selection: Record<string, number> | null;
	balance: Balance | null;
}

export interface SelectionProblem {
	code: string;
	message: string;
	role: string | null;
}

/** `POST /games/werewolf/selection/validate`. */
export interface SelectionReport {
	valid: boolean;
	problems: SelectionProblem[];
	selection: Record<string, number>;
	balance: Balance | null;
}

/** The body of `POST /matches`. */
export interface NewMatch {
	game: string;
	players: number;
	seed?: number;
	settings: Record<string, unknown>;
	turn_delay: number;
	/** false: a fair benchmark, the match neither reads nor writes memory. */
	memory: boolean;
	/** One model id per seat (config/models.yaml); without it every seat is a random bot. */
	models?: string[];
	/** One entry per seat, a model or a bot: a table that mixes them. Instead of `models`. */
	seats?: ({ kind: 'model'; model: string; personality?: string } | { kind: 'bot' })[];
	/** Must be true with `models` or a model in `seats`: the match spends money. */
	confirm_spend?: boolean;
}

/** One model of `GET /models/catalog`: every model that can take a seat. */
export interface CatalogModel {
	/** The id for POST /matches: config/models.yaml's when verified, else OpenRouter's. */
	id: string;
	openrouter_id: string;
	name: string;
	vendor: string;
	context_length: number | null;
	input_usd_per_mtok: number;
	output_usd_per_mtok: number;
	reasoning: boolean;
	moderated: boolean;
	free: boolean;
	/** In config/models.yaml: prices and behaviour checked by the team. */
	verified: boolean;
	/** Output above 10 USD per million tokens: the form warns. */
	high_price: boolean;
	/** "config/models.yaml" (checked by hand) or "openrouter list" (booked at the listed price x 1.25). */
	price_source: string;
}

export interface Catalog {
	models: CatalogModel[];
	fetched_at: string | null;
	/** Read within the last hour; false: an older copy or only the verified models. */
	fresh: boolean;
}

/** `GET /profiles/{id}/memories`: the player's own summaries of past matches. */
export interface MatchMemory {
	match_id: string;
	game_id: string;
	summary: string;
	created_at: string;
}

/** `GET /ledger/month`: what model calls cost this month and what the cap still allows. */
export interface MonthSpend {
	month: string;
	spent_micro_eur: number;
	cap_micro_eur: number;
	remaining_micro_eur: number;
}

/** A start the arena refused, with its reason (422: the game refused, 429: arena full). */
export type Refused = { state: 'refused'; status: number; detail: string };

/** One player's standing, as in `GET /leaderboard` and `GET /profiles/{id}`. */
export interface Standing {
	profile_id: string;
	name: string;
	model_id: string;
	rating: number;
	games_played: number;
	win_rate: number | null;
	average_placement: number | null;
	/** Fewer rated games than `provisional_games`: the rating is not reliable yet. */
	provisional: boolean;
}

export interface LeaderboardRow extends Standing {
	rank: number;
	/** A real model, or a random bot. */
	kind: 'model' | 'bot';
	/** Who makes the model, from config/models.yaml; null for bots and unknown models. */
	vendor: string | null;
	/** Profiles in this row: more than 1 for the grouped seats of random bots. */
	members: number;
	/** Average cost of one rated game, in millionths of a euro; null without booked calls. */
	cost_per_game_micro_eur: number | null;
	/** Share of answers the server refused (a wrong tool or an illegal move). */
	tool_error_rate: number | null;
	/** Share of answers that were a garbled call read anyway (answer_repair). */
	repaired_rate: number | null;
	/** Share of answers taken exactly as sent; refused + repaired + clean = 1. */
	clean_rate: number | null;
}

/** Who the leaderboard shows: real models (the default), random bots, or both. */
export type LeaderboardKind = 'models' | 'bots' | 'all';

export interface Leaderboard {
	/** The game shown, or null for the overall rating. */
	game: string | null;
	/** Every game with at least one rated match. */
	games: string[];
	/** Who is shown. */
	kind: LeaderboardKind;
	/** True when real models were asked for by default but none is rated: everyone is shown. */
	fallback: boolean;
	/** Rows per kind with the other filters applied. */
	counts: { models: number; bots: number };
	/** Rated games a rating needs before it counts as reliable. */
	provisional_games: number;
	/** Whether the demo profiles are included (the default is no). */
	show_demo: boolean;
	/** Demo profiles left out. */
	demo_hidden: number;
	rows: LeaderboardRow[];
}

export interface RecentMatch {
	match_id: string;
	game_id: string;
	rated_at: string;
	/** When the match itself ended; `rated_at` is when its rating was applied. */
	played_at: string;
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
}

/** What a model cost and how often the server refused its answers. */
export interface Usage {
	cost_total_micro_eur: number | null; // null while the ledger cannot be read
	cost_per_game_micro_eur: number | null;
	answers: number;
	tool_error_rate: number | null;
	repaired_rate: number | null;
	clean_rate: number | null;
}

/** `GET /models/{id}`: one model across all its matches and seats. */
export interface ModelPage {
	/** null for a model that is not in config/models.yaml. */
	model: {
		id: string;
		vendor: string | null;
		provider_model: string;
		input_usd_per_mtok: number;
		output_usd_per_mtok: number;
	} | null;
	/** The profile without a personality; null until the model has played. */
	profile_id: string | null;
	overall: Standing | null;
	/** Rated games a rating needs before it counts as reliable. */
	provisional_games: number;
	usage: Usage;
	games: (Standing & { game_id: string; usage: Usage })[];
	recent_matches: RecentMatch[];
	personalities: { profile_id: string; personality_id: string }[];
}

/** `GET /profiles/{id}/stats`: totals per game, from the logs of the rated matches. */
export interface ProfileStats {
	profile_id: string;
	games: { game_id: string; matches: number; stats: Record<string, unknown> | null }[];
}

/** `GET /profiles/{id}/relations`: what a player thinks of the others it has met. */
export interface Relations {
	profile_id: string;
	relations: {
		profile_id: string;
		name: string;
		model_id: string;
		/** -100 distrust to +100 trust. */
		trust: number;
		notes: { match_id: string; game_id: string; text: string }[];
	}[];
}

export type Unreachable = { state: 'unreachable'; reason: string };
export type ApiResult<T> = { state: 'ok'; data: T } | { state: 'not_found' } | Unreachable;
export type MatchesResult = { state: 'ok'; matches: MatchSummary[] } | Unreachable;

export interface ArenaClient {
	health(): Promise<boolean>;
	listMatches(): Promise<MatchesResult>;
	leaderboard(
		game?: string,
		kind?: LeaderboardKind,
		demo?: boolean
	): Promise<ApiResult<Leaderboard>>;
	profile(id: string): Promise<ApiResult<Profile>>;
	model(id: string): Promise<ApiResult<ModelPage>>;
	profileStats(id: string): Promise<ApiResult<ProfileStats>>;
	relations(id: string): Promise<ApiResult<Relations>>;
	memories(id: string): Promise<ApiResult<MatchMemory[]>>;
	liveState(id: string): Promise<ApiResult<LiveState>>;
	/** Pause, resume, abort or re-time a running match; `not_found` when it is not running. */
	control(id: string, command: ControlAction): Promise<ApiResult<Control | MatchRecord>>;
	/** The WebSocket URL of a match's event stream. */
	eventsUrl(id: string): string;
	replays(): Promise<ApiResult<ReplaySummary[]>>;
	/** The whole stored log of a match. */
	events(id: string): Promise<ApiResult<MatchEvent[]>>;
	/** The board after the stored turns, and what the match cost so far. */
	board(id: string): Promise<ApiResult<Board>>;
	cost(id: string): Promise<ApiResult<Cost>>;
	batch(id: string): Promise<ApiResult<BatchSummary>>;
	/** The board after the first `events` events of the log. */
	boardAt(id: string, events: number): Promise<ApiResult<Board>>;
	/** The readable play-by-play; without `spoilers`, only what every player could see. */
	transcript(id: string, spoilers: boolean, lang: 'en' | 'de'): Promise<ApiResult<Transcript>>;
	games(): Promise<ApiResult<GameInfo[]>>;
	werewolfRoles(): Promise<ApiResult<WerewolfRole[]>>;
	werewolfTemplates(players: number): Promise<ApiResult<WerewolfTemplate[]>>;
	checkSelection(
		roles: Record<string, number>,
		players: number
	): Promise<ApiResult<SelectionReport>>;
	setup(): Promise<ApiResult<SetupOptions>>;
	monthSpend(): Promise<ApiResult<MonthSpend>>;
	catalog(): Promise<ApiResult<Catalog>>;
	startMatch(match: NewMatch): Promise<{ state: 'ok'; data: MatchRecord } | Refused | Unreachable>;
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

		leaderboard(game, kind, demo) {
			const params = new URLSearchParams();
			if (game) params.set('game', game);
			if (kind) params.set('kind', kind);
			if (demo) params.set('demo', 'true');
			const query = params.size ? `?${params}` : '';
			return getJson<Leaderboard>(
				`/leaderboard${query}`,
				(body) => isObject(body) && Array.isArray(body.rows) && Array.isArray(body.games)
			);
		},

		model(id) {
			return getJson<ModelPage>(
				`/models/${encodeURIComponent(id)}`,
				(body) => isObject(body) && Array.isArray(body.games) && isObject(body.usage),
				[404]
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

		memories(id) {
			return getJson<MatchMemory[]>(
				`/profiles/${encodeURIComponent(id)}/memories`,
				Array.isArray,
				[404, 422]
			);
		},

		relations(id) {
			return getJson<Relations>(
				`/profiles/${encodeURIComponent(id)}/relations`,
				(body) => isObject(body) && Array.isArray(body.relations),
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

		board(id) {
			return getJson<Board>(
				`/matches/${encodeURIComponent(id)}/board`,
				(body) => isObject(body) && 'spec' in body,
				[404, 422]
			);
		},

		cost(id) {
			return getJson<Cost>(
				`/matches/${encodeURIComponent(id)}/cost`,
				(body) => isObject(body) && isObject(body.players),
				[404, 422]
			);
		},

		batch(id) {
			return getJson<BatchSummary>(
				`/batches/${encodeURIComponent(id)}`,
				(body) => isObject(body) && isObject(body.statuses)
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

		replays() {
			return getJson<ReplaySummary[]>('/replays', Array.isArray);
		},

		events(id) {
			return getJson<MatchEvent[]>(
				`/matches/${encodeURIComponent(id)}/events`,
				Array.isArray,
				[404, 422]
			);
		},

		boardAt(id, events) {
			return getJson<Board>(
				`/matches/${encodeURIComponent(id)}/board?events=${encodeURIComponent(events)}`,
				(body) => isObject(body) && 'spec' in body,
				[404, 422]
			);
		},

		transcript(id, spoilers, lang) {
			const query = new URLSearchParams({ spoilers: String(spoilers), lang, format: 'json' });
			return getJson<Transcript>(
				`/matches/${encodeURIComponent(id)}/transcript?${query}`,
				(body) => isObject(body) && Array.isArray(body.lines),
				[404, 422]
			);
		},

		games() {
			return getJson<GameInfo[]>('/games', Array.isArray);
		},

		werewolfRoles() {
			return getJson<WerewolfRole[]>('/games/werewolf/roles', Array.isArray);
		},

		werewolfTemplates(players) {
			return getJson<WerewolfTemplate[]>(
				`/games/werewolf/templates?players=${encodeURIComponent(players)}`,
				Array.isArray
			);
		},

		checkSelection(roles, players) {
			return getJson<SelectionReport>(
				'/games/werewolf/selection/validate',
				(body) => isObject(body) && Array.isArray(body.problems),
				[],
				{
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify({ roles, player_count: players })
				}
			);
		},

		catalog() {
			return getJson<Catalog>(
				'/models/catalog',
				(body) => isObject(body) && Array.isArray(body.models)
			);
		},

		monthSpend() {
			return getJson<MonthSpend>(
				'/ledger/month',
				(body) => isObject(body) && typeof body.remaining_micro_eur === 'number'
			);
		},

		setup() {
			return getJson<SetupOptions>(
				'/setup',
				(body) => isObject(body) && Array.isArray(body.models) && isObject(body.caps)
			);
		},

		async startMatch(match) {
			let response: Response;
			try {
				response = await get('/matches', {
					method: 'POST',
					headers: { 'content-type': 'application/json' },
					body: JSON.stringify(match)
				});
			} catch (error) {
				return { state: 'unreachable', reason: describe(error) };
			}
			const body: unknown = await response.json().catch(() => undefined);
			if (response.status === 201 && isObject(body) && typeof body.id === 'string') {
				return { state: 'ok', data: body as unknown as MatchRecord };
			}
			if ([404, 422, 429].includes(response.status)) {
				return { state: 'refused', status: response.status, detail: detailOf(body) };
			}
			return { state: 'unreachable', reason: `the arena answered ${response.status}` };
		},

		eventsUrl(id) {
			return `${root.replace(/^http/, 'ws')}/matches/${encodeURIComponent(id)}/events`;
		}
	};
}

function isObject(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** FastAPI's `detail`: a message, or a list of field errors. */
function detailOf(body: unknown): string {
	if (!isObject(body)) return 'no reason given';
	const { detail } = body;
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail)) {
		return detail
			.map((problem) => (isObject(problem) ? String(problem.msg) : String(problem)))
			.join('; ');
	}
	return 'no reason given';
}

function describe(error: unknown): string {
	if (error instanceof DOMException && error.name === 'TimeoutError') {
		return `no answer within ${TIMEOUT_MS / 1000} s`;
	}
	return 'no connection';
}
