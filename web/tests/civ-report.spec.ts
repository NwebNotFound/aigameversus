import { readFileSync } from 'node:fs';
import { type APIRequestContext } from '@playwright/test';
import { expect, test } from './routes.js';

// The Throne of Tokens Report tab (design review section 5, cards 0, 1, 12) on the civ/1
// analytics: a real model match as the served answer, and a bot match as the arena sends it.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';
const full = JSON.parse(readFileSync('src/lib/analytics/fixture-civ-spectator.json', 'utf-8'));
const open = JSON.parse(readFileSync('src/lib/analytics/fixture-civ-spoiler-free.json', 'utf-8'));

async function civMatch(request: APIRequestContext): Promise<string> {
	const match = await (
		await request.post(`${ARENA}/matches`, {
			data: { game: 'civ', players: 4, seed: 11, settings: { rounds: 12 } }
		})
	).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
	return match.id;
}

test('the Report tab tells a Civ match: verdict, who led when, and what each seat cost', async ({
	page,
	request
}) => {
	const id = await civMatch(request);
	await page.route(`**/matches/${id}/analytics*`, (route) => route.fulfill({ json: full }));
	await page.goto(`/replays/${id}?tab=analytics`);

	await expect(page.getByTestId('tab-analytics')).toHaveText('Report');
	const report = page.getByTestId('civ-report');
	await expect(report).toBeVisible();
	const [first, second] = [...full.victory.standings].sort(
		(a: { rank: number }, b: { rank: number }) => a.rank - b.rank
	);
	await expect(page.getByTestId('civ-verdict')).toContainText(
		`on points, ${first.score} to ${second.score}.`
	);
	await expect(page.getByTestId('tile-battles')).toContainText(String(full.battles.length));

	// One score line per nation, a marker per war and conquest.
	await expect(page.getByTestId('chart-line')).toHaveCount(full.nations.length);
	const wars = full.diplomacy.timeline.filter((e: { event: string }) => e.event === 'war_declared');
	await expect(page.getByTestId('chart-marker')).toHaveCount(wars.length + full.conquests.length);
	await expect(page.getByTestId('civ-score')).toContainText('led from round');

	// One row per seat, the winner first.
	const rows = page.getByTestId('civ-seats').locator('tbody tr');
	await expect(rows).toHaveCount(full.nations.length);
	await expect(rows.first()).toHaveAttribute('data-seat', first.player);
	await expect(page.getByTestId('civ-hidden')).toHaveCount(0);

	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
	if (process.env.SHOTS)
		await page.screenshot({
			path: `${process.env.SHOTS}/civ-report-${page.viewportSize()!.width}.png`,
			fullPage: true
		});
});

test('spoiler-free, the Civ Report keeps the public parts and says what is hidden', async ({
	page,
	request
}) => {
	const id = await civMatch(request);
	await page.route(`**/matches/${id}/analytics*`, (route) => route.fulfill({ json: open }));
	await page.goto(`/replays/${id}?view=spoiler-free&tab=analytics`);

	await expect(page.getByTestId('civ-verdict')).toContainText('wins');
	await expect(page.getByTestId('civ-hidden')).toBeVisible();
	await expect(page.getByTestId('chart-line')).toHaveCount(0);
	await expect(page.getByTestId('civ-seats')).toHaveCount(0);
	await expect(page.getByTestId('tile-battles')).toContainText('spectator view');
	if (process.env.SHOTS)
		await page.screenshot({
			path: `${process.env.SHOTS}/civ-report-free-${page.viewportSize()!.width}.png`,
			fullPage: true
		});
});

test("a bot Civ match's own analytics draw the report too", async ({ page, request }) => {
	const id = await civMatch(request);
	await page.goto(`/replays/${id}?tab=analytics`);
	await expect(page.getByTestId('civ-report')).toBeVisible();
	await expect(page.getByTestId('civ-verdict')).toContainText(/wins/);
	await expect(page.getByTestId('chart-line')).toHaveCount(4);
});
