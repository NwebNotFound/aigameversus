import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	ARENA_API_URL: {
		description: 'Base URL of the arena API, as seen from the web server.',
		schema: (value) => value || 'http://127.0.0.1:8100'
	},
	READ_ONLY: {
		description: '1: spectators only. No start, pause, abort or speed, and no new-match form.',
		schema: (value) => (value === '1' ? '1' : '0')
	}
});
