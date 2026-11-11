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

test('a running match reads as its players, kind and round, never as seat ids', async ({
	page,
	request
}) => {
	const arena = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';
	// Slow enough to still run while the page loads; aborted at the end.
	const started = await request.post(`${arena}/matches`, {
		data: { game: 'liars_deck', players: 3, seed: 11, turn_delay: 2 }
	});
	expect(started.ok()).toBe(true);
	const { id } = await started.json();
	try {
		await expect
			.poll(async () => {
				const board = await (await request.get(`${arena}/matches/${id}/board`)).json();
				return board.spec?.round ?? 0;
			})
			.toBeGreaterThan(0);

		await page.goto('/');

		const row = page.locator(`[data-testid="running-match"][data-match="${id}"]`);
		await expect(row.getByTestId('player-name')).toHaveText(['Bot 1', 'Bot 2', 'Bot 3']);
		await expect(row.getByTestId('kind')).toHaveText('bots');
		await expect(row.getByTestId('progress')).toHaveText(/^round \d+$/);
		// A bot match costs nothing, so no cost is shown; no seat id appears anywhere.
		await expect(row.getByTestId('cost')).toHaveCount(0);
		await expect(row).not.toContainText(/\bp[1-3]\b/);
	} finally {
		await request.post(`${arena}/matches/${id}/abort`);
	}
});
