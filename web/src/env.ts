import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	ARENA_API_URL: {
		description: 'Base URL of the arena API, as seen from the web server.',
		schema: (value) => value || 'http://127.0.0.1:8100'
	}
});
