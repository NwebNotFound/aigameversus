import { error } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { publicEvents, publicState } from '#lib/server/redact.js';
import { transcriptFor } from '#lib/server/transcript.js';
import { langOf, viewFrom } from '#lib/viewer.js';
import type { PageServerLoad } from './$types';

/** A replay as the chosen view may see it; spoiler-free pages get public data only. */
export const load: PageServerLoad = async ({ fetch, params, url }) => {
	const view = viewFrom(url.searchParams.get('view'));
	const spectator = view === 'spectator';
	const arena = createArenaClient(ARENA_API_URL, fetch);
	const [match, events] = await Promise.all([arena.liveState(params.id), arena.events(params.id)]);
	if (match.state === 'not_found' || events.state === 'not_found') {
		error(404, 'No match with this id');
	}
	const lang = match.state === 'ok' ? langOf(match.data.match.settings) : 'en';
	const [transcript, setup] = await Promise.all([
		transcriptFor(arena, params.id, spectator, lang),
		arena.setup()
	]);
	return {
		view,
		roster: setup.state === 'ok' ? setup.data.models : [],
		match: match.state === 'ok' && !spectator ? { ...match, data: publicState(match.data) } : match,
		events:
			events.state === 'ok' && !spectator ? { ...events, data: publicEvents(events.data) } : events,
		transcript
	};
};
