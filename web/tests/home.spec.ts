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

test('nothing overflows the viewport horizontally', async ({ page }) => {
	await page.goto('/');

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
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

test('the footer says what this server plays with, not a promise', async ({ page, request }) => {
	const setup = await (
		await request.get(`${process.env.ARENA_URL ?? 'http://127.0.0.1:8100'}/setup`)
	).json();

	await page.goto('/');

	const footer = page.getByTestId('footer-status');
	await expect(footer).not.toContainText('until real models are on');
	await expect(footer).toContainText(setup.model_seats ? 'Real models enabled' : 'Bots only');
});
