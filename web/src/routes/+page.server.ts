import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [matches, games] = await Promise.all([arena.listMatches(), arena.games()]);
	// A card can start a match once the arena has the game's plugin.
	const playable = games.state === 'ok' ? games.data.map((game) => game.id) : [];
	return { matches, playable };
};
