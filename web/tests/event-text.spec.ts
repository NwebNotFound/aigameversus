import { expect, test, type APIRequestContext } from '@playwright/test';

// Events read as sentences in the live view and replays (bot matches on ARENA_URL).

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

async function finished(request: APIRequestContext, body: Record<string, unknown>) {
	const match = await (await request.post(`${ARENA}/matches`, { data: body })).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status)
		.toBe('finished');
	return match.id as string;
}

for (const [game, body] of [
	['liars_deck', { game: 'liars_deck', seed: 41, players: 4 }],
	['poker', { game: 'poker', seed: 42, players: 3 }],
	['werewolf', { game: 'werewolf', seed: 43, players: 10 }]
] as const) {
	test(`every public event of a ${game} match reads as a sentence`, async ({ page, request }) => {
		const id = await finished(request, body);

		await page.goto(`/matches/${id}`);

		const publicFeed = page.getByTestId('public-feed');
		await expect(page.getByTestId('connection')).toHaveText('whole log loaded');
		await expect(publicFeed.locator('li[data-raw="true"]')).toHaveCount(0);
		await expect(publicFeed.locator('li').first()).toContainText(/^Result: 1st /);
		await expect(publicFeed).not.toContainText('placements:');
	});
}

test('the raw events stay one click away', async ({ page, request }) => {
	const id = await finished(request, { game: 'poker', seed: 44, players: 3 });
	await page.goto(`/replays/${id}`);
	const publicFeed = page.getByTestId('public-feed');
	await expect(publicFeed.locator('li').first()).toContainText('Result:');

	await page.getByLabel('Raw events').check();

	await expect(publicFeed.locator('li').first()).toContainText('match finished');
	await expect(publicFeed.locator('li').first()).toContainText('placements:');
});

test('a German match reads in German', async ({ page, request }) => {
	const id = await finished(request, {
		game: 'werewolf',
		seed: 45,
		players: 8,
		settings: { language: 'de' }
	});

	await page.goto(`/replays/${id}`);

	const publicFeed = page.getByTestId('public-feed');
	await expect(publicFeed.locator('li').first()).toContainText(/^Ergebnis: 1\. /);
	await expect(publicFeed).toContainText('Nacht 1 bricht herein.');
});

test('a game without its plugin yet is coming soon and starts nothing', async ({ page }) => {
	await page.goto('/');

	const civ = page.locator('[data-testid="game-card"][data-game="civ"]');
	await expect(civ).toContainText('Coming soon');
	await expect(civ.getByRole('link')).toHaveCount(0);
});

test('a playable game starts the new-match form with it chosen', async ({ page }) => {
	await page.goto('/');

	await page
		.locator('[data-testid="game-card"][data-game="poker"]')
		.getByRole('link', { name: 'Start a match' })
		.click();

	await expect(page).toHaveURL('/matches/new?game=poker');
	await expect(page.getByRole('radio', { name: /Poker/ })).toBeChecked();
	await expect(page.getByLabel('Number of players')).toHaveValue('2');
});
