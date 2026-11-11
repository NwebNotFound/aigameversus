import { expect, test, type Page } from '@playwright/test';

// The Werewolf role selection of the new-match form, against the arena's own
// checks (ARENA_URL, default 8100). Role names come from the role files.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

let started: string[] = [];

test.afterEach(async ({ request }) => {
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

async function openWerewolf(page: Page, players: number) {
	await page.goto('/matches/new');
	await page.getByText('Werewolf', { exact: true }).click();
	await page.getByLabel('Number of players').fill(String(players));
	await page.getByLabel('Speed').selectOption({ label: 'Slow (3 s per turn)' });
}

const role = (page: Page, id: string) =>
	page.locator(`[data-testid="werewolf-roles"] li[data-role="${id}"]`);
const count = (page: Page, id: string) => role(page, id).locator('input');

test('the classic template fills the checklist and follows the table size', async ({ page }) => {
	await openWerewolf(page, 8);

	await expect(page.getByLabel('Template')).toHaveValue('classic');
	await expect(count(page, 'werewolf')).toHaveValue('2');
	for (const id of ['seer', 'witch', 'hunter']) await expect(count(page, id)).toBeChecked();
	await expect(count(page, 'cupid')).not.toBeChecked();
	await expect(page.getByTestId('villagers')).toHaveText(/: 3$/);
	await expect(page.getByTestId('balance')).toBeVisible();

	await page.getByLabel('Number of players').fill('9');

	await expect(count(page, 'werewolf')).toHaveValue('3');
	await expect(page.getByTestId('villagers')).toHaveText(/: 3$/);
});

test('a template that needs more players cannot be chosen at a small table', async ({ page }) => {
	await openWerewolf(page, 8);
	const chaos = page.getByLabel('Template').locator('option[value="chaos"]');

	await expect(chaos).toBeDisabled();
	await expect(chaos).toContainText('from 14 players');

	await page.getByLabel('Number of players').fill('14');

	await expect(chaos).toBeEnabled();
});

test('a custom mix is checked as it changes, with the problem next to the field', async ({
	page
}) => {
	await openWerewolf(page, 8);

	await count(page, 'werewolf').fill('4');

	await expect(page.getByLabel('Template')).toHaveValue('custom');
	await expect(page.getByTestId('selection-problems')).toContainText(
		'4 wolves for 8 players; wolves must be fewer than half (at most 3)'
	);
	await expect(page.getByTestId('balance')).toHaveAttribute('data-verdict', 'wolves');

	await count(page, 'werewolf').fill('2');
	await count(page, 'cupid').check();

	await expect(page.getByTestId('selection-problems')).toHaveCount(0);
	await expect(page.getByTestId('villagers')).toHaveText(/: 2$/);
});

test('a custom mix starts a match with exactly those roles', async ({ page, request }) => {
	await openWerewolf(page, 8);
	await count(page, 'werewolf').fill('2');
	await count(page, 'hunter').uncheck();
	await count(page, 'cupid').check();
	await expect(page.getByTestId('selection-problems')).toHaveCount(0);

	await page.getByRole('button', { name: 'Start match' }).click();
	await expect(page).toHaveURL(/\/matches\/[0-9a-f-]{36}$/);
	const id = page.url().split('/').at(-1)!;
	started.push(id);

	const record = await (await request.get(`${ARENA}/matches/${id}`)).json();
	expect(record.settings).toEqual({
		language: 'de',
		roles: { werewolf: 2, seer: 1, witch: 1, cupid: 1 }
	});
	const dealt = (await (await request.get(`${ARENA}/matches/${id}/events`)).json()).find(
		(event: { type: string }) => event.type === 'roles_dealt'
	);
	expect(dealt.data.selection).toEqual({ werewolf: 2, seer: 1, witch: 1, cupid: 1, villager: 3 });
});

test('a mix that cannot be played is refused at its fields and keeps the counts', async ({
	page
}) => {
	await openWerewolf(page, 8);
	await count(page, 'werewolf').fill('5');

	await page.getByRole('button', { name: 'Start match' }).click();

	await expect(page.getByRole('alert')).toContainText('These roles cannot be played');
	await expect(page).toHaveURL('/matches/new');
	await expect(page.getByLabel('Template')).toHaveValue('custom');
	await expect(count(page, 'werewolf')).toHaveValue('5');
	await expect(page.getByTestId('selection-problems')).toContainText('5 wolves for 8 players');
});

test('the random template draws the roles from the seed', async ({ page, request }) => {
	await openWerewolf(page, 10);

	await page.getByLabel('Template').selectOption('random_balanced');

	await expect(page.getByText('The roles are drawn from the match seed')).toBeVisible();
	await expect(role(page, 'werewolf')).toHaveCount(0);

	await page.getByRole('button', { name: 'Start match' }).click();
	await expect(page).toHaveURL(/\/matches\/[0-9a-f-]{36}$/);
	const id = page.url().split('/').at(-1)!;
	started.push(id);
	const record = await (await request.get(`${ARENA}/matches/${id}`)).json();
	expect(record.settings).toEqual({ language: 'de', template: 'random_balanced' });
});

test('the role selection fits the viewport', async ({ page }) => {
	await openWerewolf(page, 16);
	await expect(count(page, 'werewolf')).toHaveValue('4');

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});
