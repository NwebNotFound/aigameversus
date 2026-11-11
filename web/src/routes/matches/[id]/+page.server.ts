import { error } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const result = await createArenaClient(ARENA_API_URL, fetch).liveState(params.id);
	if (result.state === 'not_found') error(404, 'No match with this id');
	return { result };
};
