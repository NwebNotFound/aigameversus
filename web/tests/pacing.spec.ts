import { expect, test, type APIRequestContext } from '@playwright/test';

// Pacing: a burst of instant moves is played out moment by moment, and a model that takes
// long shows as a running timer. The live stream is replayed from a real bot match: a short
// backlog first, then everything else in one burst (as instant tool calls arrive).

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

async function finishedLog(request: APIRequestContext) {
	const match = await (
		await request.post(`${ARENA}/matches`, { data: { game: 'liars_deck', players: 3, seed: 71 } })
	).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
	const log: { seq: number }[] = await (
		await request.get(`${ARENA}/matches/${match.id}/events`)
	).json();
	return { id: match.id as string, log };
}

const sse = (events: unknown[], retry = 300) =>
	`retry: ${retry}\n\n` +
	events
		.map((e) => `id: ${(e as { seq: number }).seq}\nevent: event\ndata: ${JSON.stringify(e)}\n\n`)
		.join('');

test('a burst of instant moves plays out moment by moment; a long wait is a timer', async ({
	page
}, testInfo) => {
	testInfo.setTimeout(90_000);
	const { id, log } = await finishedLog(page.request);
	const backlog = log.slice(0, 6);
	let calls = 0;
	await page.route(`**/matches/${id}/stream*`, (route) => {
		calls += 1;
		const body = calls === 1 ? sse(backlog, 1500) : calls === 2 ? sse(log) : 'retry: 60000\n\n';
		return route.fulfill({ headers: { 'content-type': 'text/event-stream' }, body });
	});
	// The match still "runs", and p2 has been asked for 30 seconds.
	await page.route(`**/matches/${id}/state*`, async (route) => {
		const response = await route.fetch();
		const body = await response.json();
		body.match.status = 'running';
		body.match.placements = null;
		body.control = {
			paused: false,
			turn_delay: 0,
			asking: [{ player: 'p2', since: new Date(Date.now() - 30_000).toISOString() }]
		};
		await route.fulfill({ response, json: body });
	});
	// Record when the number of events on screen changes.
	await page.addInitScript(() => {
		(window as unknown as { shownAt: [number, number][] }).shownAt = [];
		new MutationObserver(() => {
			const watch = document.querySelector('[data-testid="watch"]');
			const n = Number(watch?.getAttribute('data-events'));
			const seen = (window as unknown as { shownAt: [number, number][] }).shownAt;
			if (watch && seen.at(-1)?.[0] !== n) seen.push([n, performance.now()]);
		}).observe(document, {
			subtree: true,
			attributes: true,
			attributeFilter: ['data-events'],
			childList: true
		});
	});

	await page.goto(`/matches/${id}`);
	await page.getByLabel('Playback speed').selectOption({ label: '4×' });

	// The burst ends on screen in full, but not at once.
	await expect(page.getByTestId('watch')).toHaveAttribute('data-events', String(log.length), {
		timeout: 60_000
	});
	const shown = await page.evaluate(
		() => (window as unknown as { shownAt: [number, number][] }).shownAt
	);
	const afterBacklog = shown.filter(([n]) => n > backlog.length);
	expect(afterBacklog.length).toBeGreaterThan(5);
	const gaps = afterBacklog.slice(1).map(([, t], i) => t - afterBacklog[i][1]);
	// At 4× the shortest moment is 250 ms / 4, held at least the 120 ms floor.
	expect(Math.min(...gaps)).toBeGreaterThanOrEqual(110);

	// At live, the player being asked shows a running timer, not a frozen board.
	const timer = page.locator('[data-testid="cast"] li[data-seat="p2"] [data-testid="thinking"]');
	await expect(timer).toHaveText(/thinking… 3\d s/);
	const first = await timer.textContent();
	await expect.poll(() => timer.textContent(), { timeout: 5000 }).not.toBe(first);
});

test('a replay plays each moment for at least its minimum dwell, in normalised time', async ({
	page
}) => {
	const { id, log } = await finishedLog(page.request);
	await page.goto(`/replays/${id}?step=0`);
	await page.addInitScript(() => {});
	await page.evaluate(() => {
		(window as unknown as { steps: [string, number][] }).steps = [];
		const el = document.querySelector('[data-testid="position"]')!;
		new MutationObserver(() =>
			(window as unknown as { steps: [string, number][] }).steps.push([
				el.textContent ?? '',
				performance.now()
			])
		).observe(el, { characterData: true, childList: true, subtree: true });
	});
	await page.getByLabel('Speed').selectOption({ label: '4×' });
	await page.getByRole('button', { name: 'Play' }).click();
	await expect(page.getByTestId('position')).toHaveText(`Step ${log.length} of ${log.length}`, {
		timeout: 60_000
	});
	const steps = await page.evaluate(
		() => (window as unknown as { steps: [string, number][] }).steps
	);
	const gaps = steps.slice(1).map(([, t], i) => t - steps[i][1]);
	expect(steps.length).toBeGreaterThan(5);
	expect(Math.min(...gaps)).toBeGreaterThanOrEqual(110);
});
