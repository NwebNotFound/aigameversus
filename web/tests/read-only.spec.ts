import { expect, test } from '@playwright/test';

// A read-only page (the LAN spectator page, #134): the proxy sends X-AGV-Read-Only: 1, as
// READ_ONLY=1 would make the whole server. Viewers watch; nothing offers them a control.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';
const READ_ONLY = { 'X-AGV-Read-Only': '1' };

test('read-only, a running match shows no controls and the form is nowhere', async ({
	page,
	request
}) => {
	const match = await (
		await request.post(`${ARENA}/matches`, { data: { game: 'toy', turn_delay: 2 } })
	).json();
	await page.setExtraHTTPHeaders(READ_ONLY);

	await page.goto(`/matches/${match.id}`);
	await expect(page.getByTestId('read-only')).toBeVisible();
	for (const name of ['Pause', 'Resume', 'Abort'])
		await expect(page.getByRole('button', { name })).toHaveCount(0);
	await expect(page.getByLabel('Speed')).toHaveCount(0);
	await expect(page.getByRole('navigation', { name: 'Main' }).getByText('New match')).toHaveCount(
		0
	);

	await page.goto('/');
	await expect(page.getByRole('link', { name: 'Start a match' })).toHaveCount(0);

	// The server refuses what a page no longer offers: the form and every write.
	expect((await page.request.get('/matches/new', { headers: READ_ONLY })).status()).toBe(404);
	const write = await page.request.post(`/matches/${match.id}/state`, {
		headers: { ...READ_ONLY, 'content-type': 'application/json' },
		data: { action: 'abort' }
	});
	expect(write.status()).toBe(405);
	expect((await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status).toBe('running');

	await request.post(`${ARENA}/matches/${match.id}/abort`);
});

test('without the flag the controls are there', async ({ page, request }) => {
	const match = await (
		await request.post(`${ARENA}/matches`, { data: { game: 'toy', turn_delay: 2 } })
	).json();
	await page.goto(`/matches/${match.id}`);
	await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible();
	await expect(page.getByTestId('read-only')).toHaveCount(0);
	await expect(page.getByRole('navigation', { name: 'Main' }).getByText('New match')).toBeVisible();
	await request.post(`${ARENA}/matches/${match.id}/abort`);
});
