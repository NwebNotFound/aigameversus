import { error, fail, redirect } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { QUALIFY_GAMES, parseQualifyForm, repairOf } from '#lib/qualify.js';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch, params, url }) => {
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const result = await arena.model(params.id);
	if (result.state === 'not_found') error(404, 'No model with this id');
	// The statistics are those of the model's profile, read from the logs of its matches.
	const profileId = result.state === 'ok' ? result.data.profile_id : null;
	const repair = repairOf(url.searchParams.get('repair'));
	const jobId = url.searchParams.get('job');
	const [stats, setup, job, qualification] = await Promise.all([
		profileId ? arena.profileStats(profileId) : Promise.resolve(null),
		arena.setup(),
		jobId ? arena.qualification(jobId) : Promise.resolve(null),
		// Qualification of this exact model, game and repair setting: free to read.
		Promise.all(
			QUALIFY_GAMES.map(async (game) => {
				const [current, quote] = await Promise.all([
					arena.qualificationCurrent(params.id, game, repair),
					arena.qualificationQuote(params.id, game, repair)
				]);
				return { game, current, quote };
			})
		)
	]);
	return { result, stats, setup, repair, job, qualification };
};

export const actions: Actions = {
	qualify: async ({ fetch, params, request }) => {
		const form = await request.formData();
		const values = Object.fromEntries([...form.entries()].map(([k, v]) => [k, String(v)]));
		const arena = createArenaClient(ARENA_API_URL, fetch);
		const game = String(form.get('game') ?? '');
		const repair = repairOf(String(form.get('answer_repair') ?? ''));
		if (!(QUALIFY_GAMES as readonly string[]).includes(game)) {
			return fail(400, { values, game, error: 'Choose a game that has qualification cases.' });
		}
		// A fresh quote: what this click reserves now, never what the page showed before.
		const quote = await arena.qualificationQuote(params.id, game, repair);
		if (quote.state !== 'ok') {
			const why = quote.state === 'unreachable' ? quote.reason : 'no quote for this model';
			return fail(502, { values, game, error: `No quote from the arena (${why}).` });
		}
		const parsed = parseQualifyForm(form, params.id, quote.data);
		if (!parsed.ok) return fail(400, { values, game, error: parsed.error });
		const started = await arena.startQualification(parsed.job);
		if (started.state === 'refused') {
			return fail(started.status, { values, game, error: started.detail });
		}
		if (started.state === 'unreachable') {
			return fail(502, { values, game, error: `Arena unreachable (${started.reason}).` });
		}
		redirect(
			303,
			`/models/${encodeURIComponent(params.id)}?repair=${repair}&job=${started.data.id}`
		);
	}
};
