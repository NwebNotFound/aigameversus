import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { viewFrom } from '#lib/viewer.js';
import type { RequestHandler } from './$types';

/**
 * The transcript of a match for the watch screen: `?view=` and `?lang=`. A spoiler-free
 * view asks the arena with `spoilers=false`, so hidden lines never reach the browser.
 */
export const GET: RequestHandler = async ({ fetch, params, url }) => {
	const spectator = viewFrom(url.searchParams.get('view')) === 'spectator';
	const lang = url.searchParams.get('lang') === 'de' ? 'de' : 'en';
	const result = await createArenaClient(ARENA_API_URL, fetch).transcript(
		params.id,
		spectator,
		lang
	);
	if (result.state === 'not_found') error(404, 'No match with this id');
	if (result.state === 'unreachable') error(502, `Arena unreachable (${result.reason})`);
	return json(result.data);
};
