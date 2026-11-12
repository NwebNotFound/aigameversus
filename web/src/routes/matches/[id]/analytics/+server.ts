import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { viewFrom } from '#lib/viewer.js';
import type { RequestHandler } from './$types';

/**
 * The analytics of a match for the Analytics tab: `?view=`. A spoiler-free view asks the
 * arena with `spoilers=false`, which reads public events only (docs/METRICS.md), so
 * nothing a player hid reaches the browser. 404 for a game without analytics yet.
 */
export const GET: RequestHandler = async ({ fetch, params, url }) => {
	const spoilers = viewFrom(url.searchParams.get('view')) === 'spectator';
	let response: Response;
	try {
		response = await fetch(
			`${ARENA_API_URL}/matches/${encodeURIComponent(params.id)}/analytics?spoilers=${spoilers}`,
			{ signal: AbortSignal.timeout(5000) }
		);
	} catch {
		error(502, 'The arena did not answer');
	}
	if (response.status === 404) error(404, 'No analytics for this match');
	if (!response.ok) error(502, `The arena answered ${response.status}`);
	return json(await response.json());
};
