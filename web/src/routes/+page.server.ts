import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { groupByBatch, matchLine } from '#lib/match-line.js';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [matches, games, setup] = await Promise.all([
		arena.listMatches(),
		arena.games(),
		arena.setup()
	]);
	// A card can start a match once the arena has the game's plugin.
	const playable = games.state === 'ok' ? games.data.map((game) => game.id) : [];
	const roster = setup.state === 'ok' ? setup.data.models : [];
	// At most 10 matches run at a time (MAX_RUNNING), so a board and a cost each is cheap.
	// A board or cost that does not answer leaves its part of the row out, not the row.
	const lines =
		matches.state === 'ok'
			? await Promise.all(
					matches.matches.map(async (match) => {
						const [board, cost] = await Promise.all([arena.board(match.id), arena.cost(match.id)]);
						return matchLine(
							match,
							board.state === 'ok' ? board.data.spec : null,
							cost.state === 'ok' ? cost.data.total_micro_eur : null,
							roster
						);
					})
				)
			: [];
	const running = matches.state === 'ok' ? matches.matches : [];
	const entries = groupByBatch(
		running.map((match, index) => ({ match, line: lines[index] })),
		(item) => item.match.batch
	);
	const summaries = Object.fromEntries(
		await Promise.all(
			entries
				.filter((entry) => entry.batch !== null)
				.map(async (entry) => {
					const id = entry.batch!.id;
					const summary = await arena.batch(id);
					return [id, summary.state === 'ok' ? summary.data : null] as const;
				})
		)
	);
	return { matches, entries, summaries, playable };
};
