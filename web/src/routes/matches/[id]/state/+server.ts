import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient, type ArenaClient, type ControlAction } from '#lib/api.js';
import { publicState } from '#lib/server/redact.js';
import { viewFrom, type View } from '#lib/viewer.js';
import type { RequestHandler } from './$types';

/** Record, board, cost and controls of a match, for the live view to refresh after new turns. */
export const GET: RequestHandler = async ({ fetch, params, url }) => {
	return snapshot(
		createArenaClient(ARENA_API_URL, fetch),
		params.id,
		viewFrom(url.searchParams.get('view')),
		url.searchParams.get('nation')
	);
};

/** Run a control (`{action: "pause" | "resume" | "abort" | "speed", turn_delay?}`), then GET. */
export const POST: RequestHandler = async ({ fetch, params, request, url }) => {
	const command = parse(await request.json().catch(() => null));
	if (!command) error(400, 'Unknown control');
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const result = await arena.control(params.id, command);
	// not_found: the match stopped meanwhile; the snapshot shows how it ended.
	if (result.state === 'unreachable') error(502, `Arena unreachable (${result.reason})`);
	return snapshot(
		arena,
		params.id,
		viewFrom(url.searchParams.get('view')),
		url.searchParams.get('nation')
	);
};

/** `?view=spoiler-free` gets the public board (a Civ map through `?nation=`'s eyes), no seed. */
async function snapshot(arena: ArenaClient, id: string, view: View, nation: string | null) {
	const result = await arena.liveState(id);
	if (result.state === 'not_found') error(404, 'No match with this id');
	if (result.state === 'unreachable') error(502, `Arena unreachable (${result.reason})`);
	return json(view === 'spoiler-free' ? publicState(result.data, nation) : result.data);
}

function parse(body: unknown): ControlAction | null {
	if (typeof body !== 'object' || body === null) return null;
	const { action, turn_delay } = body as Record<string, unknown>;
	if (action === 'pause' || action === 'resume' || action === 'abort') return { action };
	if (action === 'speed' && typeof turn_delay === 'number') return { action, turn_delay };
	return null;
}
