import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

// The live view of bot matches. The tests start their matches on the arena API
// directly (ARENA_URL, default the Compose port 8100), as the new-match form will.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

// A route handler can still be fetching when a test ends; unrouting with ignoreErrors keeps
// its late "Test ended" rejection from failing the run.
test.afterEach(async ({ page }) => {
	await page.unrouteAll({ behavior: 'ignoreErrors' });
});

interface Started {
	id: string;
	players: string[];
}

/** Matches this worker started in the current test; aborted after it, so none keeps a place. */
let started: string[] = [];

async function start(request: APIRequestContext, body: Record<string, unknown>): Promise<Started> {
	const response = await request.post(`${ARENA}/matches`, { data: body });
	expect(response.status(), await response.text()).toBe(201);
	const match: Started = await response.json();
	started.push(match.id);
	return match;
}

test.afterEach(async ({ request }) => {
	// 409 for a match that has already stopped.
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

async function storedLog(request: APIRequestContext, id: string): Promise<{ seq: number }[]> {
	return (await request.get(`${ARENA}/matches/${id}/events`)).json();
}

async function waitUntilStopped(request: APIRequestContext, id: string) {
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${id}`)).json()).status, {
			timeout: 60_000
		})
		.not.toBe('running');
}

/**
 * How many events the page has received: the stream merges every position once. (What is
 * on screen plays out from these at reading pace; tests/pacing.spec.ts covers that.)
 */
async function shownEvents(page: Page): Promise<number> {
	return Number(await page.getByTestId('live-header').getAttribute('data-received'));
}

test('the live view follows a running match to its end, every event once', async ({
	page,
	request
}) => {
	const match = await start(request, { game: 'liars_deck', seed: 5, turn_delay: 0.3 });

	await page.goto(`/matches/${match.id}`);

	await expect(page.getByRole('heading', { level: 1, name: "Liar's Deck" })).toBeVisible();
	await expect(page.getByTestId('status')).toHaveText('running');
	await expect(page.getByTestId('connection')).toHaveText('live');
	await expect(page.getByTestId('board')).toHaveAttribute('data-layout', 'card_table');
	await expect(page.getByTestId('seat')).toHaveCount(match.players.length);
	await expect(page.getByTestId('commentary').locator('li[data-kind]').first()).toBeVisible();

	await expect(page.getByTestId('status')).toHaveText('finished', { timeout: 60_000 });
	await expect(page.getByTestId('connection')).toHaveText('whole log loaded');
	const log = await storedLog(request, match.id);
	await expect.poll(() => shownEvents(page)).toBe(log.length);
	await expect(page.getByTestId('cost')).toContainText('0.0000 €');
	await expect(page.getByRole('link', { name: 'Watch the replay →' })).toBeVisible();
	await expect(page.getByRole('group', { name: 'Controls' })).toHaveCount(0);
});

test('after a lost connection the view resumes where it stopped, every event once', async ({
	page,
	request
}) => {
	const match = await start(request, { game: 'liars_deck', seed: 6, turn_delay: 0.3 });
	await expect.poll(async () => (await storedLog(request, match.id)).length).toBeGreaterThan(5);
	const firstPart = (await storedLog(request, match.id)).slice(0, 5);
	// The first connection breaks after five events; the browser's EventSource reconnects.
	// Whether it resumes after them (Last-Event-ID, see stream.test.ts) or from the start,
	// the view must show every event once.
	let reconnects = 0;
	let broken = false;
	await page.route(`**/matches/${match.id}/stream`, async (route) => {
		if (!broken) {
			broken = true;
			const events = firstPart.map(
				(event) => `id: ${event.seq}
event: event
data: ${JSON.stringify(event)}

`
			);
			return route.fulfill({
				headers: { 'content-type': 'text/event-stream' },
				body: `retry: 200

${events.join('')}`
			});
		}
		reconnects += 1;
		return route.continue();
	});

	await page.goto(`/matches/${match.id}`);

	await expect(page.getByTestId('status')).toHaveText('finished', { timeout: 60_000 });
	await expect(page.getByTestId('connection')).toHaveText('whole log loaded');
	expect(reconnects).toBeGreaterThanOrEqual(1);
	const log = await storedLog(request, match.id);
	await expect.poll(() => shownEvents(page)).toBe(log.length);
});

test('joining a finished match shows its whole log from the start', async ({ page, request }) => {
	const match = await start(request, { game: 'toy', seed: 2 });
	await waitUntilStopped(request, match.id);

	await page.goto(`/matches/${match.id}`);

	await expect(page.getByTestId('connection')).toHaveText('whole log loaded');
	const log = await storedLog(request, match.id);
	await expect.poll(() => shownEvents(page)).toBe(log.length);
	// High Card has no board yet; the page says so instead of drawing nothing.
	await expect(page.getByTestId('no-board')).toBeVisible();
});

test('pause, speed and abort control the running match', async ({ page, request }) => {
	const match = await start(request, { game: 'liars_deck', seed: 9, turn_delay: 1 });
	await page.goto(`/matches/${match.id}`);
	const controls = page.getByRole('group', { name: 'Controls' });

	await controls.getByRole('button', { name: 'Pause' }).click();
	await expect(page.getByTestId('status')).toHaveText('paused');
	// At most the turn that was being played comes in: wait until the shown positions stop changing.
	let previous = -1;
	await expect
		.poll(
			async () => {
				const now = await shownEvents(page);
				const settled = now === previous;
				previous = now;
				return settled;
			},
			{ intervals: [1300], timeout: 20_000 }
		)
		.toBe(true);
	const atPause = await shownEvents(page);
	await page.waitForTimeout(2000);
	expect(await shownEvents(page)).toBe(atPause);

	await controls.getByRole('button', { name: 'Resume' }).click();
	await expect(page.getByTestId('status')).toHaveText('running');
	await controls.getByLabel('Speed').selectOption({ label: 'Slow (3 s)' });
	await expect(controls.getByLabel('Speed')).toHaveValue('3');
	// The select changes at once, the arena a moment later: wait for the arena, do not assume it.
	await expect
		.poll(async () => (await request.get(`${ARENA}/matches/${match.id}/control`)).json())
		.toEqual({ paused: false, turn_delay: 3 });

	await controls.getByRole('button', { name: 'Abort' }).click();
	await controls.getByRole('button', { name: 'Yes, abort' }).click();

	await expect(page.getByTestId('status')).toHaveText('aborted');
	await expect(controls).toHaveCount(0);
	await expect(page.getByTestId('connection')).toHaveText('whole log loaded');
	const record = await (await request.get(`${ARENA}/matches/${match.id}`)).json();
	expect(record.status).toBe('aborted');
});

test('the commentary filters by player, and spoiler-free hides roles and thoughts', async ({
	page,
	request
}) => {
	const match = await start(request, { game: 'werewolf', players: 8, seed: 4 });
	await waitUntilStopped(request, match.id);
	await page.goto(`/matches/${match.id}`);
	await expect(page.getByTestId('connection')).toHaveText('whole log loaded');
	const lines = page.getByTestId('commentary').locator('li[data-kind]');
	await expect(lines.first()).toBeVisible();
	const all = await lines.count();

	await page.getByTestId('commentary-player').selectOption('p1');

	const actors = await lines.evaluateAll((items) => items.map((i) => i.getAttribute('data-actor')));
	expect(actors.length).toBeGreaterThan(0);
	expect(actors.length).toBeLessThan(all);
	for (const actor of actors) expect(actor).toBe('p1');

	// Spectators see every role; spoiler-free shows none, and no private line.
	await expect(page.getByTestId('secret')).toHaveCount(0);
	await page.getByRole('link', { name: 'Spoiler-free' }).click();
	await expect(page).toHaveURL(/view=spoiler-free/);

	await expect(page.getByTestId('secret')).toHaveCount(8);
	await expect(page.getByTestId('tab-thoughts')).toHaveCount(0);
	await expect(page.locator('[data-kind="whisper"], [data-kind="thought"]')).toHaveCount(0);
	await expect(lines.first()).toBeVisible();
});

test('a running match on the home page opens its live view', async ({ page, request }) => {
	const match = await start(request, { game: 'poker', seed: 3, turn_delay: 2 });

	await page.goto('/');
	await page.locator(`a[href="/matches/${match.id}"]`).click();

	await expect(page).toHaveURL(`/matches/${match.id}`);
	await expect(page.getByRole('heading', { level: 1, name: 'Poker' })).toBeVisible();
	await expect(page.getByTestId('board')).toHaveAttribute('data-layout', 'poker_table');
});

test('an unknown match is not found', async ({ page }) => {
	const response = await page.goto('/matches/00000000-0000-0000-0000-000000000000');

	expect(response?.status()).toBe(404);
});

test('the live view fits the viewport', async ({ page, request }) => {
	const match = await start(request, { game: 'werewolf', players: 10, seed: 1 });
	await waitUntilStopped(request, match.id);
	await page.goto(`/matches/${match.id}`);
	await expect(page.getByTestId('connection')).toHaveText('whole log loaded');

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});
