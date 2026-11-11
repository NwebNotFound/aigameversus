import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient, type LeaderboardKind } from '#lib/api.js';
import type { PageServerLoad } from './$types';

const KINDS: LeaderboardKind[] = ['models', 'bots', 'all'];

export const load: PageServerLoad = async ({ fetch, url }) => {
	const game = url.searchParams.get('game') || undefined;
	const asked = url.searchParams.get('kind');
	const kind = KINDS.find((k) => k === asked);
	const board = await createArenaClient(ARENA_API_URL, fetch).leaderboard(game, kind);
	return { game: game ?? null, board };
};
