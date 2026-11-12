import { fail, redirect } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { parseForm } from '#lib/new-match.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [games, setup, werewolfRoles, month, catalog] = await Promise.all([
		arena.games(),
		arena.setup(),
		arena.werewolfRoles(),
		arena.monthSpend(),
		arena.catalog()
	]);
	return { games, setup, werewolfRoles, month, catalog };
};

export const actions: Actions = {
	default: async ({ fetch, request }) => {
		const form = await request.formData();
		// Sent back with every refusal, so the form keeps what was entered.
		const values: Record<string, string> = Object.fromEntries(
			[...form.entries()].filter(([name]) => name !== 'seat').map(([k, v]) => [k, String(v)])
		);
		const arena = createArenaClient(ARENA_API_URL, fetch);
		const games = await arena.games();
		if (games.state !== 'ok') {
			const reason = games.state === 'unreachable' ? games.reason : 'no game list';
			return fail(502, { values, errors: { form: `Arena unreachable (${reason}).` } });
		}
		// The models a seat may take: none unless the server allows paid matches.
		const setup = await arena.setup();
		// Any model of the catalog may take a seat; without the catalog, the verified ones.
		const catalog = await arena.catalog();
		const allowed = setup.state === 'ok' && setup.data.model_seats;
		const models = !allowed
			? []
			: catalog.state === 'ok'
				? catalog.data.models.map((m) => m.id)
				: setup.state === 'ok'
					? setup.data.models.map((m) => m.id)
					: [];
		const unreliable =
			catalog.state === 'ok'
				? catalog.data.models.filter((m) => m.reliability?.status === 'unreliable').map((m) => m.id)
				: [];
		const parsed = parseForm(form, games.data, models, unreliable);
		if (!parsed.ok) return fail(400, { values, errors: parsed.errors });

		const roles = parsed.match.settings.roles as Record<string, number> | undefined;
		if (roles) {
			// Problems next to their roles, before the arena refuses the match as a whole.
			const report = await arena.checkSelection(roles, parsed.match.players);
			if (report.state === 'ok' && !report.data.valid) {
				return fail(400, {
					values,
					errors: { roles: 'These roles cannot be played; see below.' },
					problems: report.data.problems
				});
			}
		}

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
