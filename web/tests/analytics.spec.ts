import { expect, test, type APIRequestContext } from '@playwright/test';

// The Analytics tab of Liar's Deck, on bot matches started on the arena (ARENA_URL).

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

async function finished(request: APIRequestContext, body: Record<string, unknown>) {
	const match = await (await request.post(`${ARENA}/matches`, { data: body })).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
	return match.id as string;
}

test('the tab draws the match and its numbers are the arena numbers', async ({ page, request }) => {
	const id = await finished(request, { game: 'liars_deck', players: 4, seed: 51 });
	const arena = await (await request.get(`${ARENA}/matches/${id}/analytics?spoilers=true`)).json();

	await page.goto(`/replays/${id}?tab=analytics`);

	const panel = page.getByTestId('analytics');
	await expect(panel.getByTestId('kpi-moves')).toHaveText(String(arena.moves.length));
	for (const chart of ['moves', 'players', 'heatmap', 'revolver', 'cards', 'response']) {
		await expect(panel.getByTestId(`chart-${chart}`)).toBeVisible();
	}
	await expect(panel.locator('[data-testid="chart-moves"] [data-seq]')).toHaveCount(
		arena.moves.length
	);
	// Bots answer at once: the chart says so instead of drawing empty bars.
	await expect(panel.getByTestId('response-empty')).toBeVisible();
	const p1 = arena.totals.p1;
	const rate = p1.lie_rate?.value == null ? '–' : `${Math.round(p1.lie_rate.value * 100)} %`;
	await expect(
		panel.locator('[data-testid="chart-players"] tr[data-player="p1"] [data-testid="lie-rate"]')
	).toHaveText(rate);
});

test('in a replay the numbers stop at the step, and a move jumps to its moment', async ({
	page,
	request
}) => {
	const id = await finished(request, { game: 'liars_deck', players: 3, seed: 52 });
	const arena = await (await request.get(`${ARENA}/matches/${id}/analytics?spoilers=true`)).json();
	const log: { seq: number }[] = await (await request.get(`${ARENA}/matches/${id}/events`)).json();
	const third = arena.moves[2];
	const step = log.findIndex((e) => e.seq === third.seq) + 1;

	await page.goto(`/replays/${id}?tab=analytics&step=${step}`);
	await expect(page.getByTestId('kpi-moves')).toHaveText('3');

	await page.locator(`[data-testid="chart-moves"] [data-seq="${arena.moves[1].seq}"]`).click();
	await expect(page.getByTestId('tab-replay')).toHaveAttribute('aria-selected', 'true');
	await expect(page.getByTestId('position')).toHaveText(
		`Step ${log.findIndex((e) => e.seq === arena.moves[1].seq) + 1} of ${log.length}`
	);
});

test('spoiler-free analytics carry no hidden truth', async ({ page, request }) => {
	const id = await finished(request, { game: 'liars_deck', players: 4, seed: 53 });
	const bodies: string[] = [];
	page.on('response', async (r) => {
		if (r.url().includes('/analytics')) bodies.push(await r.text());
	});

	await page.goto(`/replays/${id}?tab=analytics&view=spoiler-free`);
	await expect(page.getByTestId('chart-moves')).toBeVisible();

	expect(bodies.length).toBeGreaterThan(0);
	const data = JSON.parse(bodies[0]);
	expect(data.spoilers).toBe(false);
	// What needs the hidden cards is null; the revolver risk is public in both views.
	expect(data.meta?.seed ?? null).toBeNull();
	for (const totals of Object.values(data.totals) as {
		lie_rate: unknown;
		chosen_lie_rate: unknown;
	}[]) {
		expect(totals.lie_rate).toBeNull();
		expect(totals.chosen_lie_rate).toBeNull();
	}
	// A play counts as honest or a lie only once its cards were turned over.
	for (const move of data.moves.filter((m: { kind: string }) => m.kind === 'play')) {
		if (!move.called) expect(move.honest).toBeNull();
	}
});

test('live, the tab grows as turns come in', async ({ page, request }) => {
	const match = await (
		await request.post(`${ARENA}/matches`, {
			data: { game: 'liars_deck', players: 3, seed: 54, turn_delay: 0.6 }
		})
	).json();

	await page.goto(`/matches/${match.id}`);
	await page.getByTestId('tab-analytics').click();
	const moves = page.getByTestId('kpi-moves');
	await expect(moves).toBeVisible();
	const first = Number(await moves.textContent());
	await expect
		.poll(async () => Number(await moves.textContent()), { timeout: 20_000 })
		.toBeGreaterThan(first);

	await request.post(`${ARENA}/matches/${match.id}/abort`);
});

test('a game without analytics yet says so', async ({ page, request }) => {
	const id = await finished(request, { game: 'poker', players: 3, seed: 55 });
	await page.goto(`/replays/${id}?tab=analytics`);
	await expect(page.getByTestId('analytics-none')).toBeVisible();
});
