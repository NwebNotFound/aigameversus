import { fail, redirect } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { parseForm } from '#lib/new-match.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [games, setup] = await Promise.all([arena.games(), arena.setup()]);
	return { games, setup };
};

export const actions: Actions = {
	default: async ({ fetch, request }) => {
		const form = await request.formData();
		// Sent back with every refusal, so the form keeps what was entered.
		const values = Object.fromEntries(
			['game', 'players', 'seed', 'language', 'turn_delay', 'no_memory'].map((name) => [
				name,
				String(form.get(name) ?? '')
			])
		);
		const arena = createArenaClient(ARENA_API_URL, fetch);
		const games = await arena.games();
		if (games.state !== 'ok') {
			const reason = games.state === 'unreachable' ? games.reason : 'no game list';
			return fail(502, { values, errors: { form: `Arena unreachable (${reason}).` } });
		}
		const parsed = parseForm(form, games.data);
		if (!parsed.ok) return fail(400, { values, errors: parsed.errors });

		const started = await arena.startMatch(parsed.match);
		if (started.state === 'refused') {
			const message =
				started.status === 429 ? `The arena is full: ${started.detail}` : started.detail;
			return fail(started.status, { values, errors: { form: message } });
		}
		if (started.state === 'unreachable') {
			return fail(502, { values, errors: { form: `Arena unreachable (${started.reason}).` } });
		}
		redirect(303, `/matches/${started.data.id}`);
	}
};
