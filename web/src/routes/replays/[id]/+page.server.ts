import { error } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [match, events] = await Promise.all([arena.liveState(params.id), arena.events(params.id)]);
	if (match.state === 'not_found' || events.state === 'not_found') {
		error(404, 'No match with this id');
	}
	return { match, events };
};
