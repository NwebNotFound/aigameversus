import { expect, test, type APIRequestContext } from '@playwright/test';

// The bar table of Liar's Deck on seeded bot matches, started on the arena API directly.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

let started: string[] = [];

async function start(request: APIRequestContext, body: Record<string, unknown>): Promise<string> {
	const response = await request.post(`${ARENA}/matches`, { data: { game: 'liars_deck', ...body } });
	expect(response.status(), await response.text()).toBe(201);
	const match = await response.json();
	started.push(match.id);
	return match.id;
}

test.afterEach(async ({ request }) => {
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

async function log(request: APIRequestContext, id: string) {
	return (await request.get(`${ARENA}/matches/${id}/events`)).json();
}

test('the table seats every player with card count, revolver and the table card', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 4, seed: 5, turn_delay: 0.2 });

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('board')).toHaveAttribute('data-layout', 'card_table');
	await expect(page.getByTestId('seat')).toHaveCount(4);
	await expect(page.getByTestId('table-card')).toHaveText(/King|Queen|Ace/);
	await expect(page.getByTestId('card-count')).toHaveCount(4);
	await expect(page.getByTestId('revolver').first()).toContainText('/6');
	// No sideways scrolling at 375 or 1280 pixels.
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('after the match each revolver shows the shots of its player', async ({ page, request }) => {
	const id = await start(request, { players: 3, seed: 8 });
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
	const shots: Record<string, number> = {};
	for (const event of await log(request, id)) {
		if (event.type === 'trigger_pulled') shots[event.data.player] = (shots[event.data.player] ?? 0) + 1;
	}

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('seat')).toHaveCount(3);
	for (const player of ['p1', 'p2', 'p3']) {
		await expect(
			page.getByTestId('seat').filter({ hasText: player }).getByTestId('revolver')
		).toContainText(`${shots[player] ?? 0}/6`);
	}
});

test('spoilers off turns every hand and the last play into card backs', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 2, seed: 3 });
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
	await page.goto(`/matches/${id}`);
	await expect(page.getByTestId('seat')).toHaveCount(2);
	await expect(page.getByTestId('secret')).toHaveCount(0);

	await page.getByLabel('Show spoilers').uncheck();

	await expect(page.locator('.card.face')).toHaveCount(0);
	await expect(page.getByTestId('stand').getByTestId('secret')).toHaveCount(2);
	// The number of cards stays public.
	await expect(page.getByTestId('card-count')).toHaveCount(2);
});

test('a call and a shot get a banner while the match is watched', async ({ page, request }) => {
	const id = await start(request, { players: 3, seed: 5, turn_delay: 0.6 });
	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('banner')).toBeVisible({ timeout: 40_000 });
	await expect(page.getByTestId('banner')).toHaveText(/Liar!|click|BANG/);
});
