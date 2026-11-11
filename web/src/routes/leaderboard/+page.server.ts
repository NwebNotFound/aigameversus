import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, url }) => {
	const game = url.searchParams.get('game') || undefined;
	const board = await createArenaClient(ARENA_API_URL, fetch).leaderboard(game);
	return { game: game ?? null, board };
};
