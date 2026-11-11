import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

// Replays of finished bot matches started on the arena (ARENA_URL, default 8100).

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

async function finishedMatch(request: APIRequestContext, body: Record<string, unknown>) {
	const match = await (await request.post(`${ARENA}/matches`, { data: body })).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status)
		.toBe('finished');
	const record = await (await request.get(`${ARENA}/matches/${match.id}`)).json();
	const log = await (await request.get(`${ARENA}/matches/${match.id}/events`)).json();
	return { record, log: log as { seq: number; type: string }[] };
}

const shownSeqs = (page: Page) =>
	page
		.locator('[data-testid$="-feed"] li')
		.evaluateAll((items) =>
			items.map((i) => Number(i.getAttribute('data-seq'))).sort((a, b) => a - b)
		);

test('the replay list shows a finished match with its winner and links to it', async ({
	page,
	request
}) => {
	const { record } = await finishedMatch(request, { game: 'liars_deck', seed: 31, players: 3 });
	const winner = record.placements.find((p: { rank: number }) => p.rank === 1).player;

	await page.goto('/replays');

	const row = page.locator(`[data-testid="replays"] tr[data-id="${record.id}"]`);
	await expect(row).toContainText("Liar's Deck");
	await expect(row).toContainText(winner);
	await expect(row).toContainText('0.0000 €');
	await row.getByRole('link').click();
	await expect(page).toHaveURL(new RegExp(`/replays/${record.id}`));
	await expect(page.getByRole('heading', { level: 1, name: "Liar's Deck" })).toBeVisible();
});

test('the timeline steps through the log, and the board follows', async ({ page, request }) => {
	const { record, log } = await finishedMatch(request, { game: 'liars_deck', seed: 32 });

	await page.goto(`/replays/${record.id}`);

	// Opened without a step, the replay shows the whole match.
	await expect(page.getByTestId('position')).toContainText(`Step ${log.length} of ${log.length}`);
	expect(await shownSeqs(page)).toEqual(log.map((e) => e.seq));

	await page.getByRole('button', { name: 'To the start' }).click();
	await expect(page.getByTestId('position')).toHaveText(`Step 0 of ${log.length}`);
	expect(await shownSeqs(page)).toEqual([]);
	await expect(page.getByTestId('no-board').or(page.getByTestId('board'))).toBeVisible();

	for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Step forward' }).click();
	await expect(page.getByTestId('position')).toContainText(
		`Step 3 of ${log.length}: ${log[2].type.replaceAll('_', ' ')}`
	);
	expect(await shownSeqs(page)).toEqual([0, 1, 2]);
	await expect(page).toHaveURL(/step=3$/);

	await page.getByRole('button', { name: 'Step back' }).click();
	expect(await shownSeqs(page)).toEqual([0, 1]);
	await expect(page.getByTestId('board')).toBeVisible();
});

test('play runs the match forward on its own and stops at the end', async ({ page, request }) => {
	const { record, log } = await finishedMatch(request, { game: 'toy', seed: 33 });
	await page.goto(`/replays/${record.id}?step=0`);

	await page.getByLabel('Speed').selectOption({ label: '4×' });
	await page.getByRole('button', { name: 'Play' }).click();

	await expect(page.getByTestId('position')).toContainText(`Step ${log.length} of ${log.length}`, {
		timeout: 20_000
	});
	await expect(page.getByRole('button', { name: 'Play' })).toBeVisible();
});

test('a share link opens the replay at its step', async ({ page, request }) => {
	const { record, log } = await finishedMatch(request, { game: 'werewolf', seed: 34, players: 8 });

	await page.goto(`/replays/${record.id}?step=10`);

	await expect(page.getByTestId('position')).toContainText(`Step 10 of ${log.length}`);
	await expect(page.getByLabel('Share link')).toHaveValue(
		new RegExp(`/replays/${record.id}[?]step=10$`)
	);
	expect(await shownSeqs(page)).toEqual(log.slice(0, 10).map((e) => e.seq));
});

test('the JSON export holds the record and the whole log', async ({ page, request }) => {
	const { record, log } = await finishedMatch(request, { game: 'poker', seed: 35, players: 3 });
	await page.goto(`/replays/${record.id}`);

	const download = page.waitForEvent('download');
	await page.getByRole('link', { name: 'Export JSON' }).click();
	const file = await download;
	const body = JSON.parse(await (await request.get(`/replays/${record.id}/export.json`)).text());

	expect(file.suggestedFilename()).toBe(`aigameversus-poker-${record.id}.json`);
	expect(body.format).toBe('aigameversus-replay/1');
	expect(body.match).toMatchObject({ id: record.id, game: 'poker', seed: 35 });
	expect(body.events).toEqual(log);
});

test('an unknown replay is not found', async ({ page }) => {
	const response = await page.goto('/replays/00000000-0000-0000-0000-000000000000');

	expect(response?.status()).toBe(404);
});

test('the replay player fits the viewport', async ({ page, request }) => {
	const { record } = await finishedMatch(request, { game: 'werewolf', seed: 36, players: 10 });
	await page.goto(`/replays/${record.id}?step=40`);
	await expect(page.getByTestId('position')).toContainText('Step 40');

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});
