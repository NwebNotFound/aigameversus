import { expect, test } from '@playwright/test';

const GAME_NAMES = ["Liar's Deck", 'Poker', 'Werewolf', 'Throne of Tokens'];
const NAV_LINKS = ['Home', 'New match', 'Leaderboard', 'Replays'];

test('home shows the four game cards', async ({ page }) => {
	await page.goto('/');

	const cards = page.getByTestId('game-card');
	await expect(cards).toHaveCount(4);
	for (const name of GAME_NAMES) {
		await expect(cards.getByRole('heading', { name, exact: true })).toBeVisible();
	}
});

test('nav has the four sections and marks the current page', async ({ page }) => {
	await page.goto('/');

	const nav = page.getByRole('navigation', { name: 'Main' });
	for (const label of NAV_LINKS) {
		await expect(nav.getByRole('link', { name: label })).toBeVisible();
	}
	await expect(nav.getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page');
});

// The smoke test runs against the whole stack, so the arena must be reachable.
// Other tests start matches meanwhile, so the list may be empty or not.
test('the web reaches the arena and lists its running matches', async ({ page }) => {
	await page.goto('/');

	const section = page.getByRole('region', { name: 'Running matches' });
	await expect(
		section.getByTestId('no-matches').or(section.getByTestId('match-list'))
	).toBeVisible();
	await expect(section.getByTestId('arena-unreachable')).toHaveCount(0);
});

test('Replays is a coming-soon page', async ({ page }) => {
	await page.goto('/');

	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'Replays' })
		.click();

	await expect(page.getByRole('heading', { level: 1, name: 'Replays' })).toBeVisible();
	await expect(page.getByText('Coming soon', { exact: true })).toBeVisible();
});

test('nothing overflows the viewport horizontally', async ({ page }) => {
	await page.goto('/');

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});
