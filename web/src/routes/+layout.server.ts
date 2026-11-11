import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { footerLine } from '#lib/format.js';
import type { LayoutServerLoad } from './$types';

/** The footer's line about real models and this month's spend; neutral when the arena is down. */
export const load: LayoutServerLoad = async ({ fetch }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [setup, month] = await Promise.all([arena.setup(), arena.monthSpend()]);
	return {
		footer: footerLine(
			setup.state === 'ok' ? setup.data.model_seats : null,
			month.state === 'ok' ? month.data : null
		)
	};
};
