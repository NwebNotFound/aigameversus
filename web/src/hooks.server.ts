import { READ_ONLY } from '$app/env/private';
import { isReadOnly, refusal } from '#lib/server/read-only.js';
import type { Handle } from '@sveltejs/kit/hooks';

/** Read-only requests (src/lib/server/read-only.ts) never reach a write. */
export const handle: Handle = async ({ event, resolve }) => {
	event.locals.readOnly = isReadOnly(READ_ONLY, event.request.headers);
	if (event.locals.readOnly) {
		const refused = refusal(event.request.method, event.url.pathname);
		if (refused) return new Response(refused.text, { status: refused.status });
	}
	return resolve(event);
};
