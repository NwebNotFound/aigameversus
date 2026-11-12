import { expect, test } from '@playwright/test';

// The arena of these tests seats models with a dummy key: a click that passes the checks
// would make a call, so the tests only ever click with a limit the arena refuses.
const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

async function firstModel(request: import('@playwright/test').APIRequestContext) {
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	const model = setup.models[0].id as string;
	// The first quote of a game builds its fixtures (seconds): warm them before the page.
	for (const game of ['liars_deck', 'poker']) {
		await request.get(`${ARENA}/qualifications/quote`, {
			params: { model, game },
			timeout: 60_000
		});
	}
	return model;
}

test('a model page shows its qualification per game with what a test may cost', async ({
	page,
	request
}) => {
	const model = await firstModel(request);
	const quote = await (
		await request.get(`${ARENA}/qualifications/quote`, { params: { model, game: 'poker' } })
	).json();

	await page.goto(`/models/${model}`);

	const section = page.getByTestId('qualification');
	await expect(section.getByRole('heading', { name: 'Qualification' })).toBeVisible();
	const poker = page.getByTestId('qualify-poker');
	await expect(poker.getByTestId('qualify-status')).toContainText(
		/Qualified|Not qualified|Unknown/
	);
	await expect(poker.getByTestId('qualify-quote')).toContainText(`${quote.calls} calls`);
	await expect(page.getByTestId('qualify-liars_deck')).toBeVisible();
});

test('a test whose limit is below its worst case is refused and starts nothing', async ({
	page,
	request
}) => {
	const model = await firstModel(request);
	const setup = await (await request.get(`${ARENA}/setup`)).json();
	test.skip(!setup.model_seats, 'this arena does not seat models');
	await page.goto(`/models/${model}`);
	const poker = page.getByTestId('qualify-poker');

	await poker.getByRole('button', { name: 'Test this model (spends money)' }).click();
	await expect(poker.getByRole('alert')).toContainText('tick the box');

	const quote = await (
		await request.get(`${ARENA}/qualifications/quote`, { params: { model, game: 'poker' } })
	).json();
	test.skip(quote.fits_default, 'the default limit holds this worst case: a click would spend');
	await poker.getByLabel('Spend limit (euros)').fill('0.01'); // below the worst case
	await poker.getByLabel(/I understand that this test spends up to/).check();
	await poker.getByRole('button', { name: 'Test this model (spends money)' }).click();
	await expect(poker.getByRole('alert')).toContainText('raise the limit');

	const jobs = await (await request.get(`${ARENA}/qualifications`, { params: { model } })).json();
	expect(jobs).toEqual([]);
});

test('a spectator sees the status but no test button', async ({ browser, request }) => {
	const model = await firstModel(request);
	const context = await browser.newContext({ extraHTTPHeaders: { 'x-agv-read-only': '1' } });
	const page = await context.newPage();

	await page.goto(`/models/${model}`);

	await expect(page.getByTestId('qualify-poker').getByTestId('qualify-status')).toBeVisible();
	await expect(page.getByTestId('qualify-form')).toHaveCount(0);
	await context.close();
});
