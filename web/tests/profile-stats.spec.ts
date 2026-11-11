import { expect, test } from '@playwright/test';

// Game statistics on a profile page. A bot match started on the arena
// (ARENA_URL, default 8100) is rated when it ends, with its seats.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

test("a bot's profile shows its Liar's Deck statistics", async ({ page, request }) => {
	const started = await request.post(`${ARENA}/matches`, {
		data: { game: 'liars_deck', seed: 21, players: 3 }
	});
	const match = await started.json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status)
		.toBe('finished');
	const board = await (
		await request.get(`${ARENA}/leaderboard?game=liars_deck&kind=all&group_bots=false`)
	).json();
	const bot = board.rows.find((row: { name: string }) => row.name === 'Random Bot p1');
	// The bot is one profile shared by every spec: another match can finish between the API read
	// and the page load. Read both again until they agree.
	await expect(async () => {
		const stats = await (await request.get(`${ARENA}/profiles/${bot.profile_id}/stats`)).json();
		const liars = stats.games.find((g: { game_id: string }) => g.game_id === 'liars_deck');

		await page.goto(`/profiles/${bot.profile_id}`);

		const table = page.locator('[data-testid="game-stats"][data-game="liars_deck"]');
		await expect(table.locator('caption')).toHaveText(
			`Liar's Deck · ${liars.matches} ${liars.matches === 1 ? 'match' : 'matches'}`,
			{ timeout: 2000 }
		);
		await expect(table.getByRole('row', { name: /^Plays/ })).toContainText(
			String(liars.stats.plays),
			{ timeout: 2000 }
		);
		await expect(table.getByRole('row', { name: /^Lie rate/ })).toContainText(/\d+ %|–/, {
			timeout: 2000
		});
	}).toPass({ timeout: 30_000 });
});

test('a player without statistics says so', async ({ page }) => {
	// The demo players only play High Card, which has no statistics.
	await page.goto('/leaderboard?game=toy');
	// Random bots of other tests' matches are on this board too, with statistics.
	await page
		.getByTestId('leaderboard')
		.locator('tbody tr')
		.filter({ hasText: /DEMO / })
		.first()
		.getByRole('link')
		.click();

	await expect(page.getByTestId('no-game-stats')).toBeVisible();
	await expect(page.getByTestId('game-stats')).toHaveCount(0);
});
