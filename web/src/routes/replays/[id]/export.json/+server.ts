import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { RequestHandler } from './$types';

/**
 * A match as one JSON file: its record and its whole log, as spectators see it
 * (thoughts and hidden cards included). Replaying the log rebuilds the match.
 */
export const GET: RequestHandler = async ({ fetch, params }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [match, events] = await Promise.all([arena.liveState(params.id), arena.events(params.id)]);
	if (match.state === 'not_found' || events.state === 'not_found')
		error(404, 'No match with this id');
	if (match.state !== 'ok' || events.state !== 'ok') error(502, 'The arena did not answer');
	const { id, game, status, players, seed, settings, started_at, finished_at, placements } =
		match.data.match;
	return json(
		{
			format: 'aigameversus-replay/1',
			match: { id, game, status, players, seed, settings, started_at, finished_at, placements },
			cost: match.data.cost,
			events: events.data
		},
		{
			headers: {
				'content-disposition': `attachment; filename="aigameversus-${game}-${id}.json"`
			}
		}
	);
};
