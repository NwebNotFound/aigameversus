import { expect, test, type Page } from '@playwright/test';

// The "Configure" panel of a model seat in the new-match form: presets, copying between
// seats, the live estimate against the worst case. Needs an arena with model seats on
// (ARENA_ALLOW_MODEL_SEATS=1 and a key); the tests skip elsewhere. No test starts a match:
// the estimate is free, and nothing here ticks the spend box.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

test.beforeEach(async ({ request }) => {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	test.skip(!setup.model_seats, 'this server plays random bots only');
});

async function pick(page: Page, seat: string, id: string, name: string) {
	await page.getByLabel(`Player of ${seat}`).click();
	await page.getByLabel(`Search models for ${seat}`).fill(name);
	await page.getByTestId(`picker-${seat}`).locator(`li[data-id="${id}"] .option`).click();
}

async function table(page: Page, game: string, seats: ({ id: string; name: string } | null)[]) {
	await page.goto('/matches/new');
	await page.waitForLoadState('networkidle'); // hydrated: a click is handled, not lost
	await page.getByText(game, { exact: true }).click();
	await page.getByLabel('Number of players').fill(String(seats.length));
	await expect(page.getByLabel(`Player of p${seats.length}`)).toBeVisible();
	for (const [index, model] of seats.entries())
		if (model) await pick(page, `p${index + 1}`, model.id, model.name);
}

async function firstModel(request: import('@playwright/test').APIRequestContext) {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	return { setup, model: setup.models[0] as { id: string; name: string } };
}

const hidden = (page: Page, seat: string) => page.locator(`input[name="seat_config_${seat}"]`);

test('a model seat has a Configure panel with defaults, presets and help; a bot seat has none', async ({
	page,
	request
}) => {
	const { setup, model } = await firstModel(request);
	await table(page, "Liar's Deck", [model, model, null]);
	const panel = page.getByTestId('configure-p1');

	await expect(page.getByTestId('summary-p1')).toHaveText('Default');
	await expect(page.getByTestId('configure-p3')).toHaveCount(0); // a random bot
	await panel.locator('summary').click();
	if (!setup.seat_options?.length) await expect(page.getByTestId('not-live-p1')).toBeVisible();
	await expect(panel.getByText('How long a reasoning model thinks')).toBeVisible();
	await expect(page.getByTestId('option-p1-private_plan')).toHaveCount(0); // Civ only

	await panel.getByRole('button', { name: 'Careful' }).click();

	await expect(page.getByTestId('summary-p1')).toHaveText('Careful');
	await expect(panel.getByRole('button', { name: 'Careful' })).toHaveAttribute(
		'aria-pressed',
		'true'
	);
	expect(JSON.parse((await hidden(page, 'p1').inputValue()) || '{}')).toMatchObject({
		reasoning_effort: 'high',
		temperature: 0.2
	});
	await panel.getByLabel('Temperature').fill('0.7');
	await expect(page.getByTestId('summary-p1')).toHaveText(/^\d changes$/);
	await panel.getByRole('button', { name: 'Reset' }).click();
	await expect(page.getByTestId('summary-p1')).toHaveText('Default');
});

test('settings copy from one seat to another, and to every model seat at once', async ({
	page,
	request
}) => {
	const { model } = await firstModel(request);
	await table(page, "Liar's Deck", [model, model, model]);
	const p1 = page.getByTestId('configure-p1');
	await p1.locator('summary').click();
	await p1.getByRole('button', { name: 'Fast and cheap' }).click();
	const p2 = page.getByTestId('configure-p2');
	await p2.locator('summary').click();

	await p2.getByLabel('Copy settings to p2 from').selectOption('p1');

	await expect(page.getByTestId('summary-p2')).toHaveText('Fast and cheap');
	await expect(page.getByTestId('summary-p3')).toHaveText('Default');
	await p1.getByRole('button', { name: 'Aggressive' }).click();
	await p1.getByRole('button', { name: 'Apply to all seats' }).click();
	for (const seat of ['p1', 'p2', 'p3'])
		await expect(page.getByTestId(`summary-${seat}`)).toHaveText('Aggressive');
	await expect(page.getByTestId('estimate-options')).toBeVisible();
});

test('the live estimate stands next to the worst case, which the spend limit lowers', async ({
	page,
	request
}) => {
	const { setup, model } = await firstModel(request);
	await table(page, "Liar's Deck", [model, model]);
	const estimate = page.getByTestId('estimate');

	await expect(estimate.getByTestId('estimate-value')).toHaveText(/^\d+\.\d{4} €$/, {
		timeout: 30_000
	});
	await expect(estimate.getByTestId('worst-case')).toHaveText(
		`${setup.caps.match_eur.toFixed(2)} €`
	);
	await page.getByLabel('Spend limit for this match (optional, euros)').fill('0.01');
	await expect(estimate.getByTestId('worst-case')).toHaveText('0.01 €');
});

test('an answer length out of range is shown at the seat and refused at the submit', async ({
	page,
	request
}) => {
	const { model } = await firstModel(request);
	await table(page, "Liar's Deck", [model, model]);
	const p2 = page.getByTestId('configure-p2');
	await p2.locator('summary').click();

	await p2.getByLabel('Answer length').selectOption('custom');
	await p2.getByLabel('Tokens per answer for p2').fill('10');

	await expect(page.getByTestId('config-problem-p2')).toContainText('Answer length');
	await page.getByRole('button', { name: 'Start match (spends money)' }).click();
	await expect(page).toHaveURL('/matches/new'); // the spend box is not ticked either
});

test('Throne of Tokens offers the private plan, and the open panel fits the viewport', async ({
	page,
	request
}) => {
	const { model } = await firstModel(request);
	await table(page, 'Throne of Tokens', [model, model, model, model]);
	await page.getByTestId('configure-p1').locator('summary').click();

	await expect(page.getByTestId('option-p1-private_plan')).toBeVisible();
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});
