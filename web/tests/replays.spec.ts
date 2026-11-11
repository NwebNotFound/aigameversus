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

/** The positions of the commentary lines on screen, with bookkeeping shown. */
const shownSeqs = (page: Page) =>
	page
		.getByTestId('commentary')
		.locator('li[data-seq]')
		.evaluateAll((items) =>
			items.map((i) => Number(i.getAttribute('data-seq'))).sort((a, b) => a - b)
		);

/** The positions the transcript tells, up to the event at `seq`. */
async function transcriptUpTo(request: APIRequestContext, id: string, seq: number) {
	const body = await (
		await request.get(`${ARENA}/matches/${id}/transcript?spoilers=true&lang=en`)
	).json();
	return (body.lines as { seq: number | null }[])
		.map((l) => l.seq)
		.filter((s): s is number => s !== null && s <= seq)
		.sort((a, b) => a - b);
}

const stepOf = async (page: Page) =>
	Number((await page.getByTestId('position').textContent())?.match(/Step (\d+)/)?.[1]);

test('the replay list shows a finished match with its winner and links to it', async ({
	page,
	request
}) => {
	const { record } = await finishedMatch(request, { game: 'liars_deck', seed: 31, players: 3 });
	const winner = record.placements.find((p: { rank: number }) => p.rank === 1).player;

	await page.goto('/replays');

	const row = page.locator(`[data-testid="replays"] tr[data-id="${record.id}"]`);
	await expect(row).toContainText("Liar's Deck");
	// Seats read by display name: a bot in seat pN is "Bot N".
	await expect(row).toContainText(`Bot ${winner.slice(1)}`);
	await expect(row).toContainText('0.0000 €');
	await row.getByRole('link').click();
	await expect(page).toHaveURL(new RegExp(`/replays/${record.id}`));
	await expect(page.getByRole('heading', { level: 1, name: "Liar's Deck" })).toBeVisible();
});

test('the timeline steps from moment to moment, and the board follows', async ({
	page,
	request
}) => {
	const { record, log } = await finishedMatch(request, { game: 'liars_deck', seed: 32 });

	await page.goto(`/replays/${record.id}`);
	await page.getByLabel('Show bookkeeping').check();

	// Opened without a step, the replay shows the whole match: every line of the transcript.
	await expect(page.getByTestId('position')).toHaveText(`Step ${log.length} of ${log.length}`);
	expect(await shownSeqs(page)).toEqual(await transcriptUpTo(request, record.id, Infinity));
	await expect(page.getByTestId('chapters').getByRole('button').first()).toHaveText('R1');
	expect(await page.getByTestId('highlight').count()).toBeGreaterThan(0);

	await page.getByRole('button', { name: 'To the start' }).click();
	await expect(page.getByTestId('position')).toHaveText(`Step 0 of ${log.length}`);
	expect(await shownSeqs(page)).toEqual([]);
	await expect(page.getByTestId('no-board').or(page.getByTestId('board'))).toBeVisible();

	// A moment skips bookkeeping: one click can pass several events.
	for (let i = 0; i < 3; i++) await page.getByRole('button', { name: 'Next moment' }).click();
	const step = await stepOf(page);
	expect(step).toBeGreaterThanOrEqual(3);
	expect(await shownSeqs(page)).toEqual(
		await transcriptUpTo(request, record.id, log[step - 1].seq)
	);
	await expect(page).toHaveURL(new RegExp(`step=${step}$`));
	await expect(page.getByTestId('caption')).not.toHaveText('Before the first move.');

	await page.getByRole('button', { name: 'Previous moment' }).click();
	expect(await stepOf(page)).toBeLessThan(step);
	await expect(page.getByTestId('board')).toBeVisible();

	// A chapter button jumps to the start of that round.
	await page.getByTestId('chapters').getByRole('button', { name: 'R2' }).click();
	await expect(page.getByTestId('caption')).toContainText('Round 2');
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
	await page.getByLabel('Show bookkeeping').check();

	await expect(page.getByTestId('position')).toHaveText(`Step 10 of ${log.length}`);
	expect(await shownSeqs(page)).toEqual(await transcriptUpTo(request, record.id, log[9].seq));
});

test('the JSON export holds the record and the whole log', async ({ page, request }) => {
	const { record, log } = await finishedMatch(request, { game: 'poker', seed: 35, players: 3 });
	await page.goto(`/replays/${record.id}`);

	await page.getByLabel('More').click();
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
	// The commentary scrolls inside its own column: the page stays about one screen tall.
	const height = await page.evaluate(() => document.documentElement.scrollHeight);
	expect(height).toBeLessThan(page.viewportSize()!.height * 2.6);

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('a key moment gets its beat when watched, a seek stays quiet', async ({ page, request }) => {
	const { record } = await finishedMatch(request, { game: 'liars_deck', seed: 32 });
	const transcript = await (
		await request.get(`${ARENA}/matches/${record.id}/transcript?spoilers=true`)
	).json();
	const call = (transcript.lines as { seq: number; raw: { type: string } }[]).find(
		(l) => l.raw.type === 'liar_called'
	)!;

	// Opening a replay in the middle shows no beat.
	await page.goto(`/replays/${record.id}?step=${call.seq}`);
	await expect(page.getByTestId('position')).toContainText(`Step ${call.seq} of`);
	await expect(page.getByTestId('banner')).toHaveCount(0);

	// Watching the call happen does: the call-out says what the transcript says.
	await page.getByRole('button', { name: 'Next moment' }).click();
	await expect(page.getByTestId('banner')).toHaveAttribute('data-beat', 'call');
	await expect(page.getByTestId('banner')).toContainText('LIAR');

	// Jumping to the end is a seek, not watching.
	await page.getByRole('button', { name: 'To the start' }).click();
	await page.getByRole('button', { name: 'To the end' }).click();
	await page.waitForTimeout(1600);
	await expect(page.getByTestId('banner')).toHaveCount(0);
});

test('the end of a ranked match is a result card with a podium, not a paragraph', async ({
	page,
	request
}) => {
	const { record, log } = await finishedMatch(request, {
		game: 'liars_deck',
		seed: 41,
		players: 4
	});
	const winner = record.placements.find((p: { rank: number }) => p.rank === 1).player;

	await page.goto(`/replays/${record.id}`);

	const card = page.getByTestId('result');
	await expect(card).toHaveAttribute('data-kind', 'ranks');
	// The podium names the winner by display name: the bot in seat pN of a bot match is "Bot N".
	await expect(card.getByTestId('podium').locator('[data-rank="1"]')).toContainText(
		`Bot ${winner.slice(1)}`
	);
	// The caption tells the last moment, never the run-on ranking line.
	await expect(page.getByTestId('caption')).not.toContainText('Result:');
	await expect(page.getByTestId('final-ranks').locator('li')).toHaveCount(4);

	// The viewer can look at the board, and stepping back leaves the end.
	await page.getByTestId('result-close').click();
	await expect(card).toHaveCount(0);
	await page.getByRole('button', { name: 'To the start' }).click();
	await page.getByRole('button', { name: 'To the end' }).click();
	await expect(page.getByTestId('result')).toBeVisible();
	expect(log.length).toBeGreaterThan(0);
});

test('a team game ends with the winning side and its players', async ({ page, request }) => {
	const { record, log } = await finishedMatch(request, { game: 'werewolf', seed: 42, players: 8 });
	const end = log.find((e) => e.type === 'game_over') as unknown as {
		data: { winners: string[] };
	};

	await page.goto(`/replays/${record.id}`);

	const card = page.getByTestId('result');
	await expect(card).toHaveAttribute('data-kind', 'team');
	await expect(card.getByTestId('winners').locator('li')).toHaveCount(end.data.winners.length);
});

test('a poker showdown is one row per hand', async ({ page, request }) => {
	const { record, log } = await finishedMatch(request, { game: 'poker', seed: 35, players: 3 });
	const showdown = log.find((e) => e.type === 'showdown') as unknown as {
		seq: number;
		data: { hands: unknown[] };
	};
	test.skip(!showdown, 'this seed has no showdown');

	await page.goto(`/replays/${record.id}?step=${showdown.seq + 1}`);

	await expect(page.getByTestId('showdown').last().locator('.hand-row')).toHaveCount(
		showdown.data.hands.length
	);
});
