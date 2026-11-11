import { expect, test } from '@playwright/test';

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

// A model page. No model has played in the demo stack (matches started from the UI seat random
// bots), so these look at a configured model that has not played yet.

test('a model that has not played shows what it is and that it has not played', async ({
	page
}) => {
	await page.goto('/models/glm-flash');

	await expect(page.getByRole('heading', { level: 1, name: 'glm-flash' })).toBeVisible();
	await expect(page.getByTestId('model-info')).toContainText('z-ai/');
	await expect(page.getByTestId('not-played')).toBeVisible();
	await expect(page.getByTestId('summary')).toHaveCount(0);
});

test('an unknown model is not found', async ({ page }) => {
	const response = await page.goto('/models/no-such-model');

	expect(response?.status()).toBe(404);
});

// Needs a rated real model, which only a stack with real-model matches has (the CI stack seats
// random bots only): without one the test is skipped, not passed.
test('every recent match of a model shows when it was played', async ({ page, request }) => {
	const board = await (await request.get(`${ARENA}/leaderboard?kind=models`)).json();
	test.skip(board.rows.length === 0, 'no rated real model in this stack');
	const row = board.rows[0];
	const model = await (
		await request.get(`${ARENA}/models/${encodeURIComponent(row.model_id)}`)
	).json();

	await page.goto(`/models/${encodeURIComponent(row.model_id)}`);

	const matches = page.getByTestId('model-matches').locator('li');
	await expect(matches).toHaveCount(model.recent_matches.length);
	for (let i = 0; i < model.recent_matches.length; i++) {
		// the match's own end time, not the time its rating was applied
		const played: string = model.recent_matches[i].played_at;
		await expect(matches.nth(i).getByTestId('match-date')).toHaveText(
			`${played.slice(0, 10)} ${played.slice(11, 16)} UTC`
		);
	}
});
