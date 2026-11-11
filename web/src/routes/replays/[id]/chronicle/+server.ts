import { error, json } from '@sveltejs/kit';
import { ARENA_API_URL } from '$app/env/private';
import { isLang, isStyle } from '#lib/chronicle.js';
import type { RequestHandler } from './$types';

/**
 * The chronicle of a finished match, from the arena: `?style=&lang=` and `format=json`
 * (chapters) or `format=markdown` (a .md download). The arena's status is passed on:
 * 409 for a match that is still running, 404 for an unknown match or a game without one.
 */
export const GET: RequestHandler = async ({ fetch, params, url }) => {
	const style = url.searchParams.get('style') ?? 'epic';
	const lang = url.searchParams.get('lang') ?? 'en';
	const format = url.searchParams.get('format') ?? 'json';
	if (!isStyle(style) || !isLang(lang) || !['json', 'markdown'].includes(format)) {
		error(400, 'unknown style, language or format');
	}
	const query = new URLSearchParams({ style, lang, format });
	let response: Response;
	try {
		response = await fetch(
			`${ARENA_API_URL}/matches/${encodeURIComponent(params.id)}/chronicle?${query}`
		);
	} catch {
		error(502, 'The arena did not answer');
	}
	if (!response.ok)
		error(response.status === 404 || response.status === 409 ? response.status : 502);
	if (format === 'markdown') {
		return new Response(await response.text(), {
			headers: {
				'content-type': 'text/markdown; charset=utf-8',
				'content-disposition': `attachment; filename="aigameversus-chronicle-${style}-${lang}.md"`
			}
		});
	}
	return json(await response.json());
};
