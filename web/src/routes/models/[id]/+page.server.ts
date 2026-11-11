import { error } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const result = await arena.model(params.id);
	if (result.state === 'not_found') error(404, 'No model with this id');
	// The statistics are those of the model's profile, read from the logs of its matches.
	const profileId = result.state === 'ok' ? result.data.profile_id : null;
	const stats = profileId ? await arena.profileStats(profileId) : null;
	return { result, stats };
};
