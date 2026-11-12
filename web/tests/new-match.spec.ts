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

test('without model seats on the server, models are listed but not selectable', async ({
	page,
	request
}) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	test.skip(setup.model_seats, 'this server allows model seats');
	await page.goto('/matches/new');

	const seat = page.getByLabel('Player of p1');
	await expect(seat).toHaveAttribute('data-value', 'random_bot');
	await seat.click();
	const picker = page.getByTestId('picker-p1');
	for (const model of setup.models) {
		await expect(picker.locator(`li[data-id="${model.id}"] .option`)).toBeDisabled();
	}
	await expect(page.getByLabel('Personality of p1')).toBeDisabled();
	await expect(
		page.getByText('This server plays random bots only: it was not started')
	).toBeVisible();
	await expect(page.getByTestId('spend')).toHaveCount(0);
	await expect(page.getByText('Bots cost nothing.')).toBeVisible();
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

// A form post that the action itself refuses (a bad seed), so no match starts.
const REFUSED_FORM = {
	game: 'liars_deck',
	players: '2',
	seat: 'random_bot',
	language: 'de',
	turn_delay: '1',
	seed: '-1'
};

for (const origin of ['http://127.0.0.1:3100', 'http://localhost:3100']) {
	test(`a form post from ${origin} reaches the form`, async ({ request }) => {
		const response = await request.post('/matches/new', {
			headers: { origin },
			form: REFUSED_FORM,
			maxRedirects: 0
		});

		expect(response.status()).toBe(400);
	});
}

test('a form post from a foreign origin is refused', async ({ request }) => {
	const response = await request.post('/matches/new', {
		headers: { origin: 'https://attacker.example' },
		form: REFUSED_FORM,
		maxRedirects: 0
	});

	expect(response.status()).toBe(403);
});

test('a match can be played without memory', async ({ page, request }) => {
	await page.goto('/matches/new');
	await page.getByText('Poker', { exact: true }).click();
	await page.getByLabel('Play without memory (fair benchmark)').check();
	const id = await submit(page);

	const record = await (await request.get(`${ARENA}/matches/${id}`)).json();
	expect(record.memory).toBe(false);
});
