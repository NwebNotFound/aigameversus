import { error } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { publicState } from '#lib/server/redact.js';
import { viewFrom } from '#lib/viewer.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params, url }) => {
	const view = viewFrom(url.searchParams.get('view'));
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [result, setup] = await Promise.all([arena.liveState(params.id), arena.setup()]);
	const roster = setup.state === 'ok' ? setup.data.models : [];
	if (result.state === 'not_found') error(404, 'No match with this id');
	if (result.state === 'ok' && view === 'spoiler-free') {
		return { view, roster, result: { ...result, data: publicState(result.data) } };
	}
	return { view, roster, result };
};
