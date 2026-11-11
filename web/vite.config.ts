import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// A Node server, so pages can call the arena API server-side (D-030).
			adapter: adapter(),
			// Form posts are refused from any origin but ORIGIN (CSRF check). The
			// local stack answers on both names of this machine (D-054).
			csrf: { trustedOrigins: ['http://127.0.0.1:3100', 'http://localhost:3100'] }
		})
	],
	test: {
		include: ['src/**/*.test.ts']
	}
});
