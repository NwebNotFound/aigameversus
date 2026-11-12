import { readFileSync } from 'node:fs';
import { type Page } from '@playwright/test';
import { expect, rewrite, test } from './routes.js';

// The Throne of Tokens board (`hex_map`, docs/civ-interfaces.md). The plugin is not built yet,
// so a running match's board is swapped for a map from the real generator (fixture).

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';
const MAP = JSON.parse(readFileSync('src/lib/boards/fixture-hex-map.json', 'utf-8'));
const NATIONS = MAP.nations.map((n: { id: string }) => n.id);

/** Serve `spec` as the board of the match, as the arena would once the plugin exists. */
async function withMap(page: Page, id: string, spec: Record<string, unknown>) {
	await rewrite(page, `**/matches/${id}/state*`, (body) => {
		body.board = { ...body.board, spec };
		body.match.players = NATIONS;
	});
}

test('the hex map draws every tile, city, army and battle, and shows a nation its fog', async ({
	page,
	request
}) => {
	const match = await (
		await request.post(`${ARENA}/matches`, { data: { game: 'toy', turn_delay: 2 } })
	).json();
	await withMap(page, match.id, MAP);
	await page.goto(`/matches/${match.id}`);

	const board = page.locator('[data-layout="hex_map"]');
	await expect(board).toBeVisible({ timeout: 15_000 });
	await expect(page.getByTestId('hex-tile')).toHaveCount(MAP.cols * MAP.rows);
	await expect(page.getByTestId('hex-city')).toHaveCount(MAP.cities.length);
	await expect(page.getByTestId('hex-army')).toHaveCount(MAP.armies.length);
	await expect(page.getByTestId('hex-battle')).toHaveCount(MAP.battles.length);
	await expect(page.getByTestId('hex-front')).toHaveCount(MAP.wars.length);
	await expect(page.getByTestId('hex-round')).toHaveText(String(MAP.round));
	await expect(page.getByTestId('hex-nations').locator('li')).toHaveCount(NATIONS.length);
	await expect(page.getByTestId('hex-stock')).toHaveCount(NATIONS.length);

	// Through one nation's eyes, what it does not see this round is dimmed and hides its armies.
	const unseen = (MAP.fog.p1 as string[]).join('').split('0').length - 1;
	await page.getByTestId('hex-eyes').selectOption({ label: await nationName(page, 'p1') });
	await expect(page.locator('[data-testid="hex-tile"].fogged')).toHaveCount(unseen);
	const own = page.locator('[data-testid="hex-army"][data-owner="p1"]');
	await expect(own).toHaveCount(
		MAP.armies.filter((a: { owner: string }) => a.owner === 'p1').length
	);

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
	if (process.env.SHOTS) {
		await page.getByTestId('hex-eyes').selectOption({ index: 0 });
		await board.screenshot({ path: `${process.env.SHOTS}/hex-${page.viewportSize()!.width}.png` });
		await page.getByTestId('hex-eyes').selectOption({ index: 1 });
		await board.screenshot({
			path: `${process.env.SHOTS}/hex-fog-${page.viewportSize()!.width}.png`
		});
	}
	await request.post(`${ARENA}/matches/${match.id}/abort`);
});

test('spoiler-free, the map has no fog switch, stocks or unit lists', async ({ page, request }) => {
	const match = await (
		await request.post(`${ARENA}/matches`, { data: { game: 'toy', turn_delay: 2 } })
	).json();
	// What the web server's allowlist leaves of the map (checked in redact.test.ts).
	const { fog: _fog, ...rest } = MAP;
	const free = {
		...rest,
		armies: MAP.armies.map(({ units: _units, ...army }: Record<string, unknown>) => army),
		nations: MAP.nations.map(({ stock: _stock, ...nation }: Record<string, unknown>) => nation)
	};
	await withMap(page, match.id, free);
	await page.goto(`/matches/${match.id}?view=spoiler-free`);

	await expect(page.locator('[data-layout="hex_map"]')).toBeVisible({ timeout: 15_000 });
	await expect(page.getByTestId('hex-eyes')).toHaveCount(0);
	await expect(page.getByTestId('hex-stock')).toHaveCount(0);
	await expect(page.getByTestId('hex-army')).toHaveCount(MAP.armies.length);
	await expect(page.locator('[data-testid="hex-army"] title').first()).not.toContainText(
		'spearman'
	);
	await request.post(`${ARENA}/matches/${match.id}/abort`);
});

async function nationName(page: Page, id: string): Promise<string> {
	return (await page
		.locator(`[data-testid="hex-nations"] li[data-nation="${id}"] strong`)
		.textContent())!.trim();
}
