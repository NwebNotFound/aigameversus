import { expect, test, type APIRequestContext } from '@playwright/test';

// The chronicle tab on the replay page, on seeded bot matches started on the arena API.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

let started: string[] = [];

async function start(request: APIRequestContext, body: Record<string, unknown>): Promise<string> {
	const response = await request.post(`${ARENA}/matches`, { data: body });
	expect(response.status(), await response.text()).toBe(201);
	const match = await response.json();
	started.push(match.id);
	return match.id;
}

async function finished(request: APIRequestContext, id: string) {
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
}

test.afterEach(async ({ request }) => {
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

test('the chronicle tab tells a finished match in a chosen style and language', async ({
	page,
	request
}) => {
	const id = await start(request, { game: 'liars_deck', seed: 5, players: 3 });
	await finished(request, id);
	const log = await (await request.get(`${ARENA}/matches/${id}/events`)).json();
	const rounds = log.filter((e: { type: string }) => e.type === 'round_started').length;

	await page.goto(`/replays/${id}`);
	await page.getByTestId('tab-chronicle').click();

	await expect(page.getByTestId('chronicle-story')).toBeVisible();
	await expect(page.getByTestId('chronicle-chapter')).toHaveCount(rounds);
	await expect(page.getByTestId('chronicle-story')).toContainText('p1');
	await expect(page.getByRole('heading', { level: 2 })).toContainText("Liar's Deck");

	await page.getByTestId('chronicle-style').selectOption('news');
	await page.getByTestId('chronicle-lang').selectOption('de');

	await expect(page.getByTestId('chronicle-story')).toHaveAttribute('lang', 'de');
	await expect(page.getByTestId('chronicle-chapter').first()).toHaveText(/^Runde 1/);
	await expect(page.getByTestId('chronicle-story')).toContainText('Tischkarte');
});

test('the .md download is the same story as Markdown', async ({ page, request }) => {
	const id = await start(request, { game: 'poker', seed: 2, players: 3 });
	await finished(request, id);

	await page.goto(`/replays/${id}?tab=chronicle`);
	await expect(page.getByTestId('chronicle-story')).toBeVisible();
	await page.getByTestId('chronicle-style').selectOption('sports');
	await expect(page.getByTestId('chronicle-story')).toContainText('Match Commentary');

	const href = await page.getByTestId('chronicle-download').getAttribute('href');
	const response = await request.get(new URL(href!, page.url()).toString());
	expect(response.status()).toBe(200);
	expect(response.headers()['content-disposition']).toContain(
		'aigameversus-chronicle-sports-en.md'
	);
	const markdown = await response.text();
	expect(markdown).toMatch(/^# Poker: Match Commentary/);
	expect(markdown).toContain('\n## Hand 1\n');
});

test('a running match says its chronicle does not exist yet', async ({ page, request }) => {
	const id = await start(request, { game: 'liars_deck', seed: 5, players: 3, turn_delay: 2 });

	await page.goto(`/replays/${id}?tab=chronicle`);

	await expect(page.getByTestId('chronicle-problem')).toContainText('not over yet');
	await expect(page.getByTestId('chronicle-problem')).toHaveAttribute('data-status', '409');
	await expect(page.getByTestId('chronicle-download')).toHaveCount(0);
});

test('a game without a chronicle says so', async ({ page, request }) => {
	const id = await start(request, { game: 'toy', seed: 1 });
	await finished(request, id);

	await page.goto(`/replays/${id}?tab=chronicle`);

	await expect(page.getByTestId('chronicle-problem')).toContainText('no chronicle');
});

test('the tab fits the viewport and the replay tab still works', async ({ page, request }) => {
	const id = await start(request, { game: 'werewolf', seed: 3, players: 8 });
	await finished(request, id);

	await page.goto(`/replays/${id}`);
	await page.getByTestId('tab-chronicle').click();
	await expect(page.getByTestId('chronicle-story')).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);

	await page.getByTestId('tab-replay').click();
	await expect(page.getByTestId('position')).toBeVisible();
	await expect(page.getByTestId('chronicle')).toHaveCount(0);
});

test('with spoilers off the chronicle stays closed until the viewer shows them', async ({
	page,
	request
}) => {
	const id = await start(request, { game: 'werewolf', seed: 3, players: 8 });
	await finished(request, id);
	const log = await (await request.get(`${ARENA}/matches/${id}/events`)).json();
	const roles: string[] = [
		...new Set<string>(
			log
				.filter((e: { type: string }) => e.type === 'role_assigned')
				.map((e: { data: { role: string } }) => e.data.role.replaceAll('_', ' '))
		)
	].filter((role) => !['villager', 'werewolf'].includes(role)); // 'werewolf' is the game's name too

	await page.goto(`/replays/${id}`);
	await page.getByLabel('Show spoilers').uncheck();
	await page.getByTestId('tab-chronicle').click();

	// The switch is still there on this tab, the story is closed and no role name is on the page.
	await expect(page.getByLabel('Show spoilers')).not.toBeChecked();
	await expect(page.getByTestId('chronicle-spoilers')).toContainText('names hidden roles');
	await expect(page.getByTestId('chronicle-story')).toHaveCount(0);
	await expect(page.getByTestId('chronicle-download')).toHaveCount(0);
	const text = (await page.locator('body').innerText()).toLowerCase();
	for (const role of roles) expect(text).not.toContain(role);

	await page.getByTestId('chronicle-reveal').click();

	await expect(page.getByLabel('Show spoilers')).toBeChecked();
	await expect(page.getByTestId('chronicle-story')).toBeVisible();
	await expect(page.getByTestId('chronicle-download')).toBeVisible();
	const story = (await page.getByTestId('chronicle-story').innerText()).toLowerCase();
	expect(roles.some((role) => story.includes(role))).toBe(true);
});
