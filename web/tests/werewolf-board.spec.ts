import { expect, test, type APIRequestContext } from '@playwright/test';

// The Werewolf circle on seeded bot matches, started on the arena API directly.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

let started: string[] = [];

async function start(request: APIRequestContext, body: Record<string, unknown>): Promise<string> {
	const response = await request.post(`${ARENA}/matches`, {
		data: { game: 'werewolf', ...body }
	});
	expect(response.status(), await response.text()).toBe(201);
	const match = await response.json();
	started.push(match.id);
	return match.id;
}

test.afterEach(async ({ request }) => {
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

async function finished(request: APIRequestContext, id: string) {
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
}

async function log(request: APIRequestContext, id: string) {
	return (await request.get(`${ARENA}/matches/${id}/events`)).json();
}

test('the circle seats every player and shows a night or day backdrop', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3, turn_delay: 0.2 });

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('board')).toHaveAttribute('data-layout', 'player_circle');
	await expect(page.getByTestId('seat')).toHaveCount(8);
	await expect(page.getByTestId('board')).toHaveAttribute('data-theme', /night|dusk|day/);
	await expect(page.getByTestId('phase')).toHaveText(/Night|Day|Game over/);
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('after the match roles and deaths on the circle are those of the stored log', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3 });
	await finished(request, id);
	const events = await log(request, id);
	const roles = new Map<string, string>(
		events
			.filter((e: { type: string }) => e.type === 'role_assigned')
			.map((e: { data: { player: string; role: string } }) => [e.data.player, e.data.role])
	);
	const dead = events.filter((e: { type: string }) => e.type === 'player_died').length;

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('phase')).toHaveText('Game over');
	for (const [player, role] of roles) {
		const word = role.replaceAll('_', ' ');
		await expect(
			page.getByTestId('seat').filter({ hasText: player }).getByTestId('role')
		).toHaveText(new RegExp(`^${word}$`, 'i'));
	}
	await expect(page.locator('.seat.dead')).toHaveCount(dead);
});

test('spoilers off turn every role into a question mark', async ({ page, request }) => {
	const id = await start(request, { players: 6, seed: 7 });
	await finished(request, id);
	await page.goto(`/matches/${id}`);
	await expect(page.getByTestId('seat')).toHaveCount(6);
	await expect(page.getByTestId('role')).toHaveCount(6);

	await page.getByLabel('Show spoilers').uncheck();

	await expect(page.getByTestId('role')).toHaveCount(0);
	await expect(page.getByTestId('secret')).toHaveCount(6);
});

test('the votes of the day are drawn as arrows while the match is watched', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3, turn_delay: 0.3 });
	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('vote-arrow').first()).toBeAttached({ timeout: 45_000 });
	await expect(page.getByTestId('vote-count').first()).toBeVisible();
});
