import { error } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [result, stats, relations] = await Promise.all([
		arena.profile(params.id),
		arena.profileStats(params.id),
		arena.relations(params.id)
	]);
	if (result.state === 'not_found') error(404, 'No player with this id');
	return { result, stats, relations };
};
