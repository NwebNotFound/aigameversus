import { ARENA_API_URL } from '$app/env/private';
import { createArenaClient } from '#lib/api.js';
import { relay } from '#lib/stream.js';
import type { RequestHandler } from './$types';

/**
 * The event stream of a match as server-sent events, for the browser's EventSource.
 *
 * The web server follows the arena's WebSocket, so the browser never talks to the
 * arena (D-030). A reconnecting EventSource sends `Last-Event-ID`; the relay then
 * skips the positions the browser already has.
 */
export const GET: RequestHandler = ({ params, request }) => {
	const url = createArenaClient(ARENA_API_URL).eventsUrl(params.id);
	const lastSeen = Number.parseInt(request.headers.get('last-event-id') ?? '', 10);
	return new Response(relay(url, Number.isNaN(lastSeen) ? -1 : lastSeen), {
		headers: {
			'content-type': 'text/event-stream',
			'cache-control': 'no-cache',
			'x-accel-buffering': 'no'
		}
	});
};
