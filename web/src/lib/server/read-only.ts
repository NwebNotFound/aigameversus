/**
 * A read-only web server, for spectators who may watch but not act (the LAN page, #134):
 * no start, pause, abort or speed, and no new-match form. Read-only is the whole server with
 * `READ_ONLY=1`, or one request that carries `X-AGV-Read-Only: 1`, which the LAN proxy sets
 * on every request it passes on (deploy/lan/nginx.conf). The header can only take rights
 * away, so a client that sends it gains nothing.
 */
export const READ_ONLY_HEADER = 'x-agv-read-only';

export function isReadOnly(env: string | undefined, headers: Headers): boolean {
	return env === '1' || headers.get(READ_ONLY_HEADER) === '1';
}

/** Why a read-only request is refused, or null when it may pass. */
export function refusal(method: string, pathname: string): { status: number; text: string } | null {
	if (method !== 'GET' && method !== 'HEAD')
		return { status: 405, text: 'This page is read-only: spectators can watch, not act.' };
	if (pathname === '/matches/new' || pathname.startsWith('/matches/new/'))
		return { status: 404, text: 'Not found' };
	return null;
}
