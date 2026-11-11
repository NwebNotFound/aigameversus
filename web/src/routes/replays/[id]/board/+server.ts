import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { RequestHandler } from './$types';

/** The board after the first `?events=N` events, for the replay player. */
export const GET: RequestHandler = async ({ fetch, params, url }) => {
	const events = Number(url.searchParams.get('events'));
	if (!Number.isInteger(events) || events < 0) error(400, 'events must be a whole number');
	const board = await createArenaClient(ARENA_API_URL, fetch).boardAt(params.id, events);
	if (board.state === 'not_found') error(404, 'No match with this id');
	if (board.state === 'unreachable') error(502, `Arena unreachable (${board.reason})`);
	return json(board.data);
};
