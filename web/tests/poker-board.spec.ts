import { expect, test, type APIRequestContext } from '@playwright/test';

// The Poker table on seeded bot matches, started on the arena API directly.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

let started: string[] = [];

async function start(request: APIRequestContext, body: Record<string, unknown>): Promise<string> {
	const response = await request.post(`${ARENA}/matches`, {
		data: { game: 'poker', ...body }
	});
	expect(response.status(), await response.text()).toBe(201);
	const match = await response.json();
	started.push(match.id);
	return match.id;
}

test.afterEach(async ({ request }) => {
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

async function finished(request: APIRequestContext, id: string) {
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
}

test('the table seats every player with stack and community slots', async ({ page, request }) => {
	const id = await start(request, { players: 6, seed: 4, turn_delay: 0.2 });

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('board')).toHaveAttribute('data-layout', 'poker_table');
	await expect(page.getByTestId('seat')).toHaveCount(6);
	await expect(page.getByTestId('stack')).toHaveCount(6);
	await expect(page.getByTestId('pot')).toContainText('Pot');
	await expect(page.getByTestId('position').first()).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('stacks on the table are the chips of the stored match', async ({ page, request }) => {
	const id = await start(request, { players: 3, seed: 9 });
	await finished(request, id);

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('seat')).toHaveCount(3);
	// Chips are never created: the stacks add up to what the players started with.
	const stacks = await page
		.getByTestId('stack')
		.locator('.amount')
		.allTextContents()
		.then((texts) => texts.map(Number));
	expect(stacks.every(Number.isFinite)).toBe(true);
	expect(stacks.reduce((a, b) => a + b, 0)).toBe(3000);
});

test('spoilers off turn hole cards into backs and hide the win chances', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 3, seed: 2, turn_delay: 0.4 });
	await page.goto(`/matches/${id}`);
	await expect(page.getByTestId('seat')).toHaveCount(3);
	await expect(page.getByTestId('win-chance').first()).toBeVisible({ timeout: 20_000 });
	await expect(page.getByTestId('win-chance').first()).toContainText('% to win');
	await expect(page.getByTestId('secret')).toHaveCount(0);

	await page.getByRole('link', { name: 'Spoiler-free' }).click();
	await expect(page).toHaveURL(/view=spoiler-free/);

	await expect(page.getByTestId('win-chance')).toHaveCount(0);
	await expect(page.getByTestId('seat').first().locator('.card.face')).toHaveCount(0);
	await expect(page.getByTestId('secret').first()).toBeVisible();
});
