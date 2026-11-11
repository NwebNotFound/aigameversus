import { expect, test } from '@playwright/test';

// The launch form with model seats on. Needs an arena started with
// ARENA_ALLOW_MODEL_SEATS=1 and an API key in its environment; the tests skip
// on any other server (CI's stack plays bots only). No test starts a match of
// models: every submit here is refused by the form before anything is sent.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

test.beforeEach(async ({ request }) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	test.skip(!setup.model_seats, 'this server plays random bots only');
});

async function chooseModels(page: import('@playwright/test').Page, ids: string[]) {
	await page.goto('/matches/new');
	await page.getByText("Liar's Deck", { exact: true }).click();
	await page.getByLabel('Number of players').fill(String(ids.length));
	for (const [index, id] of ids.entries()) {
		await page.getByLabel(`Player of p${index + 1}`).selectOption(id);
	}
}

test('a model seat shows what the match may cost and what the month has left', async ({
	page,
	request
}) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	const month = await (await request.get(`${ARENA}/ledger/month`)).json();
	const [first] = setup.models;

	await chooseModels(page, [first.id, first.id]);

	const spend = page.getByTestId('spend');
	await expect(spend).toContainText('This match spends real money.');
	await expect(page.getByTestId('match-cap')).toHaveText(`${setup.caps.match_eur.toFixed(2)} €`);
	await expect(page.getByTestId('month')).toContainText(
		`${(month.remaining_micro_eur / 1_000_000).toFixed(2)} € left`
	);
	await expect(page.getByRole('button', { name: 'Start match (spends money)' })).toBeVisible();
	await expect(
		page.getByLabel('Player of p1').locator(`option[value="${first.id}"]`)
	).toContainText(first.name);
});

test('a match of models does not start without the spend box', async ({ page, request }) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	const [first] = setup.models;
	await chooseModels(page, [first.id, first.id]);

	await page.getByRole('button', { name: 'Start match (spends money)' }).click();

	await expect(
		page.getByText('A match of models spends real money: tick the box to start it.')
	).toBeVisible();
	await expect(page).toHaveURL('/matches/new');
});

test('bots and models do not mix at one table', async ({ page, request }) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	await chooseModels(page, [setup.models[0].id, 'random_bot']);
	await page.getByLabel(/I understand that this match spends money/).check();

	await page.getByRole('button', { name: 'Start match (spends money)' }).click();

	await expect(
		page.getByText('Choose a model for every seat, or a bot for every seat: no mixed tables yet.')
	).toBeVisible();
	await expect(page).toHaveURL('/matches/new');
});
