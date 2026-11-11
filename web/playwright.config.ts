import { defineConfig, devices } from '@playwright/test';

// Runs against a UI that is already up, normally the Compose stack on port 3100
// (`docker compose up --build --wait`). Override with WEB_URL.
export default defineConfig({
	testDir: 'tests',
	fullyParallel: true,
	// The arena plays at most 10 matches at a time; more workers can hit its 429 limit.
	workers: 2,
	forbidOnly: !!process.env.CI,
	retries: process.env.CI ? 1 : 0,
	reporter: process.env.CI ? [['github'], ['list']] : 'list',
	use: {
		baseURL: process.env.WEB_URL ?? 'http://127.0.0.1:3100',
		trace: 'retain-on-failure'
	},
	projects: [
		{
			name: 'mobile-375',
			use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 812 } }
		},
		{
			name: 'desktop-1280',
			use: { ...devices['Desktop Chrome'], viewport: { width: 1280, height: 800 } }
		}
	]
});
