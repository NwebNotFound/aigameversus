import { expect, test, type Page } from '@playwright/test';

// The launch form with model seats on. Needs an arena started with
// ARENA_ALLOW_MODEL_SEATS=1 and an API key in its environment; the tests skip
// on any other server (CI's stack plays bots only). No test starts a match of
// models: every submit here is refused by the form before anything is sent.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

test.beforeEach(async ({ request }) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	test.skip(!setup.model_seats, 'this server plays random bots only');
});

/** Pick a model for a seat through its picker: search, then click it. */
async function pick(page: Page, seat: string, id: string, name: string) {
	await page.getByLabel(`Player of ${seat}`).click();
	await page.getByLabel(`Search models for ${seat}`).fill(name);
	await page.getByTestId(`picker-${seat}`).locator(`li[data-id="${id}"] .option`).click();
}

async function chooseModels(page: Page, models: { id: string; name: string }[]) {
	await page.goto('/matches/new');
	await page.getByText("Liar's Deck", { exact: true }).click();
	await page.getByLabel('Number of players').fill(String(models.length));
	for (const [index, model] of models.entries())
		await pick(page, `p${index + 1}`, model.id, model.name);
}

test('a model seat shows what the match may cost and what the month has left', async ({
	page,
	request
}) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	const month = await (await request.get(`${ARENA}/ledger/month`)).json();
	const [first] = setup.models;

	await chooseModels(page, [first, first]);

	await expect(page.getByLabel('Player of p1')).toContainText(first.name);
	await expect(page.getByTestId('spend')).toContainText('This match spends real money.');
	await expect(page.getByTestId('match-cap')).toHaveText(`${setup.caps.match_eur.toFixed(2)} €`);
	await expect(page.getByTestId('month')).toContainText(
		`${(month.remaining_micro_eur / 1_000_000).toFixed(2)} € left`
	);
	await expect(page.getByRole('button', { name: 'Start match (spends money)' })).toBeVisible();
});

test('a match of models does not start without the spend box', async ({ page, request }) => {
	const [first] = (await (await request.get(`${ARENA}/setup`)).json()).models;
	await chooseModels(page, [first, first]);

	await page.getByRole('button', { name: 'Start match (spends money)' }).click();

	await expect(
		page.getByText('A match of models spends real money: tick the box to start it.')
	).toBeVisible();
	await expect(page).toHaveURL('/matches/new');
});

test('bots and models do not mix at one table', async ({ page, request }) => {
	const [first] = (await (await request.get(`${ARENA}/setup`)).json()).models;
	await chooseModels(page, [first]);
	await page.getByLabel('Number of players').fill('2');
	await page.getByLabel(/I understand that this match spends money/).check();

	await page.getByRole('button', { name: 'Start match (spends money)' }).click();

	await expect(
		page.getByText('Choose a model for every seat, or a bot for every seat: no mixed tables yet.')
	).toBeVisible();
	await expect(page).toHaveURL('/matches/new');
});

test('the picker searches and filters the whole catalog', async ({ page, request }) => {
	const catalog = (await (await request.get(`${ARENA}/models/catalog`)).json()).models;
	const verified = catalog.filter((m: { verified: boolean }) => m.verified);
	await page.goto('/matches/new');
	await page.getByLabel('Player of p1').click();
	const picker = page.getByTestId('picker-p1');

	await picker.getByLabel('Verified').check();
	await expect(picker.getByTestId('picker-count')).toHaveText(
		`${verified.length} ${verified.length === 1 ? 'model' : 'models'}`
	);
	await page.getByLabel('Search models for p1').fill(verified[0].name);
	await expect(picker.locator(`li[data-id="${verified[0].id}"]`)).toBeVisible();
	await page.getByLabel('Search models for p1').fill('no model is called like this');
	await expect(picker.getByTestId('picker-count')).toHaveText('0 models');
});

test('shortcuts fill the seats, and an expensive or unverified model is called out', async ({
	page,
	request
}) => {
	const catalog = (await (await request.get(`${ARENA}/models/catalog`)).json()).models;
	await page.goto('/matches/new');
	await page.getByText("Liar's Deck", { exact: true }).click();
	await page.getByLabel('Number of players').fill('3');

	await page.getByRole('button', { name: 'Fill with cheap models' }).click();
	for (const seat of ['p1', 'p2', 'p3']) {
		await expect(page.getByLabel(`Player of ${seat}`)).not.toHaveAttribute(
			'data-value',
			'random_bot'
		);
	}

	const pricey = catalog.find((m: { high_price: boolean }) => m.high_price);
	test.skip(!pricey, 'the catalog has no high-price model');
	await pick(page, 'p1', pricey.id, pricey.name);
	await page.getByRole('button', { name: 'Same as p1 in every seat' }).click();
	for (const seat of ['p2', 'p3']) {
		await expect(page.getByLabel(`Player of ${seat}`)).toHaveAttribute('data-value', pricey.id);
	}
	await expect(page.getByTestId('high-price')).toContainText(pricey.name);
	if (!pricey.verified) await expect(page.getByTestId('unverified')).toContainText(pricey.name);
});

test('a favourite stays a favourite after a reload', async ({ page, request }) => {
	const [first] = (await (await request.get(`${ARENA}/setup`)).json()).models;
	await page.goto('/matches/new');
	await page.getByLabel('Player of p1').click();
	await page.getByLabel(`Mark ${first.name} as favourite`).click();

	await page.reload();
	await page.getByLabel('Player of p1').click();
	await page.getByTestId('picker-p1').getByLabel('Favourites').check();

	await expect(page.getByTestId('picker-p1').locator('li')).toHaveCount(1);
	await expect(page.getByLabel(`Unmark ${first.name} as favourite`)).toBeVisible();
});
