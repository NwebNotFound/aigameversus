import { expect, test } from '@playwright/test';

// Needs demo data: `docker compose exec arena python -m arena.ratings.demo_seed`
// (CI does this after starting the stack). Demo profiles play High Card (`toy`).

test('overall leaderboard lists the demo players by rating', async ({ page }) => {
	await page.goto('/leaderboard');

	const tabs = page.getByRole('navigation', { name: 'Games' });
	await expect(tabs.getByRole('link', { name: 'Overall' })).toHaveAttribute('aria-current', 'page');
	await expect(tabs.getByRole('link', { name: 'High Card' })).toBeVisible();

	const rows = page.getByTestId('leaderboard').locator('tbody tr');
	await expect(rows).toHaveCount(6);
	await expect(rows.first().getByRole('link')).toHaveText(/^DEMO /);

	const ratings = await rows.locator('td.strong').allInnerTexts();
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
	await expect(page.getByTestId('leaderboard').locator('tbody tr')).toHaveCount(6);
});

test('a game without matches shows the empty state', async ({ page }) => {
	await page.goto('/leaderboard?game=poker');

	await expect(page.getByTestId('empty-leaderboard')).toContainText(
		'Nobody has a rating in Poker yet.'
	);
});

test('a player links to a profile with rating bars and stats', async ({ page }) => {
	await page.goto('/leaderboard');
	const first = page.getByTestId('leaderboard').locator('tbody tr').first().getByRole('link');
	const name = await first.innerText();

	await first.click();

	await expect(page.getByRole('heading', { level: 1, name })).toBeVisible();
	await expect(page.getByTestId('rating-bars').getByText('High Card')).toBeVisible();
	await expect(page.getByRole('region', { name: 'Statistics' })).toContainText('Win rate');
	await expect(page.getByText('not available yet')).toBeVisible();
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
