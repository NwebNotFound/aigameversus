import { expect, test } from '@playwright/test';

// Needs demo data: `docker compose exec arena python -m arena.ratings.demo_seed`
// (CI does this after starting the stack). Demo profiles play High Card (`toy`).

test('overall leaderboard lists the demo players by rating', async ({ page }) => {
	await page.goto('/leaderboard');

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
	await page.goto('/leaderboard');

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
	await page.goto('/leaderboard');
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
