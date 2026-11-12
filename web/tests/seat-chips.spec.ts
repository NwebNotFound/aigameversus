import { expect, test, rewrite } from './routes.js';

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
	await rewrite(page, `**/matches/${match.id}/state*`, (body) => {
		body.match.seats = seats;
		body.cost = { total_micro_eur: 1200, players: { p1: 1200 } };
	});
	await rewrite(page, `**/matches/${match.id}/transcript*`, (body) => {
		body.players = { p1: { name: null, model: null }, p2: { name: 'Random Bot p2', model: null } };
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
	// A bot is "Bot <seat number>" with "Random Bot" under it; its seat id is not its name.
	await expect(bot).toContainText('Bot 2');
	await expect(bot).toContainText('Random Bot');
	await expect(bot).not.toContainText('p2');

	await request.post(`${ARENA}/matches/${match.id}/abort`);
});

test('in a 4-model match no visible text names a seat id, except the seat badges', async ({
	page,
	request
}) => {
	const match = await (
		await request.post(`${ARENA}/matches`, {
			data: { game: 'liars_deck', players: 4, seed: 12, turn_delay: 0.3 }
		})
	).json();
	const models = ['gpt-luna', 'gemini-flash-lite', 'gpt-luna', 'qwen-flash'];
	const seats = Object.fromEntries(
		models.map((m, i) => [`p${i + 1}`, { name: m, model_id: m, kind: 'model' }])
	);
	await rewrite(page, `**/matches/${match.id}/state*`, (body) => {
		body.match.seats = seats;
	});
	await rewrite(page, `**/matches/${match.id}/transcript*`, (body) => {
		body.players = Object.fromEntries(
			Object.keys(seats).map((s) => [s, { name: null, model: null }])
		);
	});

	await page.goto(`/matches/${match.id}`);
	await expect(page.getByTestId('commentary').locator('li[data-kind]').nth(8)).toBeVisible({
		timeout: 30_000
	});
	// The same model twice gets a suffix, so every seat stays tellable.
	await expect(page.getByTestId('cast')).toContainText('gpt-luna #2');

	const visible = await page.evaluate(() => {
		const badges = new Set(document.querySelectorAll('[data-testid="seat-badge"]'));
		const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
		const texts: string[] = [];
		for (let node = walker.nextNode(); node; node = walker.nextNode()) {
			const parent = node.parentElement;
			if (!parent || [...badges].some((b) => b.contains(parent))) continue;
			if (parent.closest('script, style, [aria-hidden="true"], .sr-only')) continue;
			if (!parent.checkVisibility()) continue;
			texts.push(node.textContent ?? '');
		}
		return texts.join(' ');
	});
	expect(visible).not.toMatch(/\bp[1-9]\b/);

	await request.post(`${ARENA}/matches/${match.id}/abort`);
});
