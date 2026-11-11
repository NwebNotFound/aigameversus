import { expect, test } from '@playwright/test';

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

// Needs demo data: `docker compose exec arena python -m arena.ratings.demo_seed`
// (CI does this after starting the stack). Demo profiles play High Card (`toy`).

test('overall leaderboard lists the demo players by rating', async ({ page }) => {
	await page.goto('/leaderboard?kind=all&demo=1');

	const tabs = page.getByRole('navigation', { name: 'Games' });
	await expect(tabs.getByRole('link', { name: 'Overall' })).toHaveAttribute('aria-current', 'page');
	await expect(tabs.getByRole('link', { name: 'High Card' })).toBeVisible();

	// Bot matches of other tests rate their random bots too; the demo players are six.
	const all = page.getByTestId('leaderboard').locator('tbody tr');
	const rows = all.filter({ hasText: /DEMO / });
	await expect(rows).toHaveCount(6);

	const ratings = await all.locator('td.strong').allInnerTexts();
	const values = ratings.map(Number);
	expect(values).toEqual([...values].sort((a, b) => b - a));
});

test('a game tab shows that game', async ({ page }) => {
	await page.goto('/leaderboard?demo=1');

	await page
		.getByRole('navigation', { name: 'Games' })
		.getByRole('link', { name: 'High Card' })
		.click();

	await expect(page).toHaveURL(/game=toy/);
	await expect(page.getByRole('link', { name: 'High Card' })).toHaveAttribute(
		'aria-current',
		'page'
	);
	await expect(
		page.getByTestId('leaderboard').locator('tbody tr').filter({ hasText: /DEMO / })
	).toHaveCount(6);
});

// Other tests play bot matches of every game with a plugin; Throne of Tokens has none yet.
test('a game without matches shows the empty state', async ({ page }) => {
	await page.goto('/leaderboard?game=civ');

	await expect(page.getByTestId('empty-leaderboard')).toContainText(
		'Nobody has a rating in Throne of Tokens yet.'
	);
});

test('a player links to a profile with rating bars and stats', async ({ page }) => {
	await page.goto('/leaderboard?demo=1');
	const first = page
		.getByTestId('leaderboard')
		.locator('tbody tr')
		.filter({ hasText: /DEMO / })
		.first()
		.getByRole('link');
	const name = await first.innerText();

	await first.click();

	await expect(page.getByRole('heading', { level: 1, name })).toBeVisible();
	await expect(page.getByTestId('rating-bars').getByText('High Card')).toBeVisible();
	await expect(page.getByRole('region', { name: 'Statistics', exact: true })).toContainText(
		'Win rate'
	);
	await expect(page.getByTestId('no-memories')).toBeVisible();
});

test('a malformed profile id is the same 404 page', async ({ page }) => {
	const response = await page.goto('/profiles/not-a-uuid');

	expect(response?.status()).toBe(404);
	await expect(page.getByText('No player with this id')).toBeVisible();
	await expect(page.getByTestId('arena-unreachable')).toHaveCount(0);
});

test('an unknown profile is a 404 page', async ({ page }) => {
	const response = await page.goto('/profiles/00000000-0000-0000-0000-000000000000');

	expect(response?.status()).toBe(404);
});

for (const path of ['/leaderboard', '/leaderboard?game=toy']) {
	test(`${path} does not overflow horizontally`, async ({ page }) => {
		await page.goto(path);

		const overflow = await page.evaluate(
			() => document.documentElement.scrollWidth - document.documentElement.clientWidth
		);
		expect(overflow).toBeLessThanOrEqual(0);
	});
}

// No real model is rated in the demo stack, so the default view falls back to everyone.
test('real models are the default and the filter can show bots or all', async ({ page }) => {
	await page.goto('/leaderboard?demo=1');

	const filter = page.getByRole('navigation', { name: 'Who' });
	// Real models are asked for; none is rated, so the board shows everyone and says so.
	await expect(filter.getByTestId('kind-all')).toHaveAttribute('aria-current', 'page');
	await expect(page.getByTestId('kind-fallback')).toContainText('No rated real-model matches yet');
	await expect(
		page.getByTestId('leaderboard').locator('tbody tr').filter({ hasText: /DEMO / })
	).toHaveCount(6);

	await filter.getByTestId('kind-models').click();
	await expect(page).toHaveURL(/kind=models/);
	await expect(page.getByTestId('empty-leaderboard')).toBeVisible();

	await filter.getByTestId('kind-bots').click();
	await expect(filter.getByTestId('kind-bots')).toHaveAttribute('aria-current', 'page');
	await expect(page.getByTestId('leaderboard')).toBeVisible();
});

test('demo data is hidden until the switch is used', async ({ page }) => {
	await page.goto('/leaderboard?kind=all');

	const demo = page.getByTestId('leaderboard').locator('tbody tr').filter({ hasText: /DEMO / });
	await expect(demo).toHaveCount(0);
	await expect(page.getByTestId('demo-switch')).toContainText('6 demo profiles hidden');

	await page.getByTestId('demo-toggle').click();

	await expect(page).toHaveURL(/demo=1/);
	await expect(demo).toHaveCount(6);
	await expect(page.getByTestId('demo-toggle')).toHaveText('Hide demo data');
});

test('the table shows model, cost per game and tool errors, and bot seats are one row', async ({
	page
}) => {
	await page.goto('/leaderboard?kind=all');

	const headers = await page.getByTestId('leaderboard').locator('th').allInnerTexts();
	expect(headers.join(' ')).toMatch(/Cost per game/i);
	expect(headers.join(' ')).toMatch(/Tool errors/i);
	const seatRows = page
		.getByTestId('leaderboard')
		.locator('tbody tr')
		.filter({ hasText: /Random Bot p\d/ });
	await expect(seatRows).toHaveCount(0);
});

// Needs a rated real model whose name is its model id (every configured model without a
// personality); skipped on a stack without one.
test('a model named like its id shows the name once, then the vendor', async ({
	page,
	request
}) => {
	const board = await (await request.get(`${ARENA}/leaderboard?kind=models`)).json();
	const row = board.rows.find((r: { name: string; model_id: string }) => r.name === r.model_id);
	test.skip(!row, 'no rated real model in this stack');

	await page.goto('/leaderboard?kind=models');

	const line = page.getByTestId('leaderboard').locator('tbody tr').filter({ hasText: row.name });
	const text = await line.first().innerText(); // hidden columns are not part of the text
	expect(text.split(row.model_id).length - 1).toBe(1);
	if (row.vendor) expect(text).toContain(row.vendor);
});

// The demo stack has both kinds of rows: the demo players have played a few games each, and the
// grouped Random Bot row adds up every bot seat of every spec. Other specs finish matches
// meanwhile, so read the API and the page together until they agree.
test('a rating from fewer than 10 games carries a provisional badge, one from 10 or more none', async ({
	page,
	request
}) => {
	await expect(async () => {
		const board = await (await request.get(`${ARENA}/leaderboard?kind=all&demo=true`)).json();
		type Row = { provisional: boolean; games_played: number };
		const provisional = board.rows.filter((row: Row) => row.provisional);
		const established = board.rows.filter((row: Row) => !row.provisional);
		// Without both kinds of row this spec would pass with the badge removed.
		expect(provisional.length, 'a row with fewer than 10 games').toBeGreaterThan(0);
		expect(established.length, 'a row with 10 or more games').toBeGreaterThan(0);
		expect(
			board.rows.every((row: Row) => row.provisional === row.games_played < board.provisional_games)
		).toBe(true);

		await page.goto('/leaderboard?kind=all&demo=1');

		const rows = page.getByTestId('leaderboard').locator('tbody tr');
		await expect(rows).toHaveCount(board.rows.length, { timeout: 2000 });
		for (let i = 0; i < board.rows.length; i++) {
			const badge = rows.nth(i).getByTestId('provisional');
			await expect(badge).toHaveCount(board.rows[i].provisional ? 1 : 0, { timeout: 2000 });
		}
		await expect(page.getByTestId('provisional').first()).toHaveAttribute(
			'title',
			`fewer than ${board.provisional_games} rated games: the rating is not reliable yet`
		);
	}).toPass({ timeout: 30_000 });
});
