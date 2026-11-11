import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient, type ApiResult } from '#lib/api.js';
import type { RequestHandler } from './$types';

/** The Werewolf templates at a table of `?players=N`, for the role selection of the form. */
export const GET: RequestHandler = async ({ fetch, url }) => {
	const players = Number(url.searchParams.get('players'));
	if (!Number.isInteger(players) || players < 1) error(400, 'players must be a whole number');
	return answer(await createArenaClient(ARENA_API_URL, fetch).werewolfTemplates(players));
};

/** Check a selection (`{roles, players}`): problems, the filled selection and its balance. */
export const POST: RequestHandler = async ({ fetch, request }) => {
	const body = await request.json().catch(() => null);
	const players = body?.players;
	const roles = body?.roles;
	if (!Number.isInteger(players) || typeof roles !== 'object' || roles === null) {
		error(400, 'Send {roles, players}');
	}
	return answer(await createArenaClient(ARENA_API_URL, fetch).checkSelection(roles, players));
};

function answer<T>(result: ApiResult<T>) {
	if (result.state !== 'ok') error(502, 'The arena did not answer');
	return json(result.data);
}
