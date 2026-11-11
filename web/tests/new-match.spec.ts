import { expect, test, type Page } from '@playwright/test';

// The new-match form starts real bot matches on the arena (ARENA_URL, default 8100).

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

let started: string[] = [];

test.afterEach(async ({ request }) => {
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

/** Submit the form and return the id of the match it opened. */
async function submit(page: Page): Promise<string> {
	await page.getByRole('button', { name: 'Start match' }).click();
	await expect(page).toHaveURL(/\/matches\/[0-9a-f-]{36}$/);
	const id = page.url().split('/').at(-1)!;
	started.push(id);
	return id;
}

test('the nav opens the form', async ({ page }) => {
	await page.goto('/');

	await page
		.getByRole('navigation', { name: 'Main' })
		.getByRole('link', { name: 'New match' })
		.click();

	await expect(page).toHaveURL('/matches/new');
	await expect(page.getByRole('heading', { level: 1, name: 'New match' })).toBeVisible();
});

test('the form starts a bot match and opens its live view', async ({ page, request }) => {
	await page.goto('/matches/new');

	await page.getByText('Poker', { exact: true }).click();
	await page.getByLabel('Number of players').fill('3');
	await page.getByLabel('Speed').selectOption({ label: 'Max (0 s per turn)' });
	await page.getByLabel('Seed').fill('11');
	const id = await submit(page);

	await expect(page.getByRole('heading', { level: 1, name: 'Poker' })).toBeVisible();
	const record = await (await request.get(`${ARENA}/matches/${id}`)).json();
	expect(record).toMatchObject({ game: 'poker', players: ['p1', 'p2', 'p3'], seed: 11 });
	expect(record.settings).toEqual({});
});

test('Werewolf gets the language, German by default', async ({ page, request }) => {
	await page.goto('/matches/new');
	await page.getByText('Werewolf', { exact: true }).click();
	await expect(page.getByLabel('Language')).toHaveValue('de');

	await page.getByLabel('Language').selectOption('en');
	await page.getByLabel('Speed').selectOption({ label: 'Slow (3 s per turn)' });
	const id = await submit(page);

	const record = await (await request.get(`${ARENA}/matches/${id}`)).json();
	expect(record.game).toBe('werewolf');
	expect(record.players).toHaveLength(6);
	expect(record.settings).toMatchObject({ language: 'en' });
	const control = await (await request.get(`${ARENA}/matches/${id}/control`)).json();
	expect(control.turn_delay).toBe(3);
});

test('a game sets the range of players and one seat per player', async ({ page }) => {
	await page.goto('/matches/new');
	const count = page.getByLabel('Number of players');

	await page.getByText('Werewolf', { exact: true }).click();
	await expect(count).toHaveValue('6');
	await expect(count).toHaveAttribute('max', '16');
	await expect(page.getByTestId('seats').locator('li')).toHaveCount(6);

	await count.fill('9');
	await expect(page.getByTestId('seats').locator('li')).toHaveCount(9);

	await page.getByText("Liar's Deck", { exact: true }).click();
	await expect(count).toHaveValue('2');
	await expect(page.getByTestId('seats').locator('li')).toHaveCount(2);
});

test('models, personalities and the cost limit are shown but not yet selectable', async ({
	page,
	request
}) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	await page.goto('/matches/new');

	const seat = page.getByLabel('Player of p1');
	await expect(seat).toHaveValue('random_bot');
	for (const model of setup.models) {
		await expect(seat.locator(`option[value="${model.id}"]`)).toBeDisabled();
	}
	const personality = page.getByLabel('Personality of p1');
	await expect(personality).toBeDisabled();
	await expect(personality.locator('option')).toHaveCount(setup.personalities.length + 1);
	const cost = page.getByLabel('Cost limit (€)');
	await expect(cost).toBeDisabled();
	await expect(cost).toHaveValue(String(setup.caps.match_eur));
});

test('a refused field is marked next to it and the form keeps what was entered', async ({
	page
}) => {
	await page.goto('/matches/new');
	await page.getByText('Werewolf', { exact: true }).click();
	await page.getByLabel('Number of players').fill('8');
	await page.getByLabel('Language').selectOption('en');
	// Past the browser's own check, as a request without the page would be.
	await page.locator('form').evaluate((form: HTMLFormElement) => (form.noValidate = true));
	await page.getByLabel('Seed').fill('-1');

	await page.getByRole('button', { name: 'Start match' }).click();

	await expect(
		page.getByText('A seed is a whole number from 0, or empty for a random one.')
	).toBeVisible();
	await expect(page).toHaveURL('/matches/new');
	await expect(page.getByLabel('Number of players')).toHaveValue('8');
	await expect(page.getByLabel('Language')).toHaveValue('en');
	await expect(page.getByLabel('Seed')).toHaveValue('-1');
});

test('the form fits the viewport', async ({ page }) => {
	await page.goto('/matches/new');
	await page.getByText('Werewolf', { exact: true }).click();

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});
