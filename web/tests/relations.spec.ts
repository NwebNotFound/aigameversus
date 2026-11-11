import { expect, test } from '@playwright/test';

// Trust between players on the profile page, from a Werewolf bot match started on
// the arena (ARENA_URL, default 8100). The server sets trust from what happened.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

test("a bot's profile lists who it trusts and why", async ({ page, request }) => {
	const match = await (
		await request.post(`${ARENA}/matches`, { data: { game: 'werewolf', players: 8, seed: 4 } })
	).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status)
		.toBe('finished');
	const board = await (await request.get(`${ARENA}/leaderboard?game=werewolf`)).json();
	const bot = board.rows.find((row: { name: string }) => row.name === 'Random Bot p1');
	const { relations } = await (
		await request.get(`${ARENA}/profiles/${bot.profile_id}/relations`)
	).json();
	expect(relations.length).toBeGreaterThan(0);

	await page.goto(`/profiles/${bot.profile_id}`);

	const items = page.getByTestId('relations').locator('li');
	await expect(items).toHaveCount(relations.length);
	const first = items.first();
	await expect(first.getByRole('link')).toHaveText(relations[0].name);
	await expect(first).toHaveAttribute('data-trust', String(relations[0].trust));
	await expect(first).toContainText(relations[0].notes[0].text);
});

test('a player nobody has met says so', async ({ page }) => {
	await page.goto('/leaderboard?game=toy');
	await page
		.getByTestId('leaderboard')
		.locator('tbody tr')
		.filter({ hasText: /DEMO / })
		.first()
		.getByRole('link')
		.click();

	await expect(page.getByTestId('no-relations')).toBeVisible();
});

test("a bot's profile lists its memories of past matches, linked to their replays", async ({
	page,
	request
}) => {
	const match = await (
		await request.post(`${ARENA}/matches`, { data: { game: 'werewolf', players: 8, seed: 5 } })
	).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status)
		.toBe('finished');
	const board = await (await request.get(`${ARENA}/leaderboard?game=werewolf`)).json();
	const bot = board.rows.find((row: { name: string }) => row.name === 'Random Bot p2');
	const memories = await (await request.get(`${ARENA}/profiles/${bot.profile_id}/memories`)).json();
	const mine = memories.find((m: { match_id: string }) => m.match_id === match.id);

	await page.goto(`/profiles/${bot.profile_id}`);

	// Found by its replay link: both viewport runs play this seed, with the same summary.
	const item = page
		.getByTestId('memories')
		.locator('li')
		.filter({ has: page.locator(`a[href="/replays/${match.id}"]`) });
	await expect(item).toHaveCount(1);
	await expect(item).toContainText(mine.summary);
	await expect(item.getByRole('link')).toHaveText('Werewolf');
});
