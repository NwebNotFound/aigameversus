import { expect, test } from '@playwright/test';

// The player chips of the watch screen: a model seat always shows its model, never "bot".
// A real model match costs money, so the live page's own state refresh is answered with
// model seats here; the transcript still says nothing about them, as for a running match.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

test('model seats show the model and are never called bots', async ({ page, request }) => {
	const match = await (
		await request.post(`${ARENA}/matches`, {
			data: { game: 'liars_deck', players: 2, seed: 9, turn_delay: 0.5 }
		})
	).json();
	const seats = {
		p1: { name: 'gemini-flash-lite', model_id: 'gemini-flash-lite', kind: 'model' },
		p2: { name: 'Random Bot p2', model_id: null, kind: 'bot' }
	};
	await page.route(`**/matches/${match.id}/state*`, async (route) => {
		const response = await route.fetch();
		const body = await response.json();
		body.match.seats = seats;
		body.cost = { total_micro_eur: 1200, players: { p1: 1200 } };
		await route.fulfill({ response, json: body });
	});
	await page.route(`**/matches/${match.id}/transcript*`, async (route) => {
		const response = await route.fetch();
		const body = await response.json();
		body.players = { p1: { name: null, model: null }, p2: { name: 'Random Bot p2', model: null } };
		await route.fulfill({ response, json: body });
	});

	await page.goto(`/matches/${match.id}`);

	const model = page.locator('[data-testid="cast"] li[data-seat="p1"]');
	const bot = page.locator('[data-testid="cast"] li[data-seat="p2"]');
	await expect(model).toHaveAttribute('data-kind', 'model');
	await expect(model).toContainText('gemini-flash-lite');
	await expect(model).toContainText('model');
	await expect(model).not.toContainText(/\bbot\b/i);
	await expect(model).toContainText('0.0012 €');
	await expect(bot).toHaveAttribute('data-kind', 'bot');
	await expect(bot).toContainText('Random Bot p2');

	await request.post(`${ARENA}/matches/${match.id}/abort`);
});
