import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { RequestHandler } from './$types';

/**
 * The live estimate of the new-match form: `{game, models, settings}` to the arena's free
 * `POST /matches/estimate`. Read-only requests never reach it (src/hooks.server.ts).
 */
export const POST: RequestHandler = async ({ fetch, request }) => {
	const body = await request.json().catch(() => null);
	const models = body?.models;
	if (
		typeof body?.game !== 'string' ||
		!Array.isArray(models) ||
		!models.length ||
		!models.every((m: unknown) => m === null || typeof m === 'string')
	) {
		error(400, 'Send {game, models, settings}');
	}
	const settings = typeof body.settings === 'object' && body.settings ? body.settings : {};
	const result = await createArenaClient(ARENA_API_URL, fetch).estimate({
		game: body.game,
		models,
		settings
	});
	if (result.state === 'ok') return json(result.data);
	if (result.state === 'refused') error(result.status, result.detail);
	error(502, 'The arena did not answer');
};
