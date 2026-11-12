import { type APIRequestContext } from '@playwright/test';
import { expect, test } from './routes.js';

// The Werewolf circle on seeded bot matches, started on the arena API directly.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

let started: string[] = [];

async function start(request: APIRequestContext, body: Record<string, unknown>): Promise<string> {
	const response = await request.post(`${ARENA}/matches`, {
		data: { game: 'werewolf', ...body }
	});
	expect(response.status(), await response.text()).toBe(201);
	const match = await response.json();
	started.push(match.id);
	return match.id;
}

test.afterEach(async ({ request }) => {
	await Promise.all(started.map((id) => request.post(`${ARENA}/matches/${id}/abort`)));
	started = [];
});

async function finished(request: APIRequestContext, id: string) {
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
}

async function log(request: APIRequestContext, id: string) {
	return (await request.get(`${ARENA}/matches/${id}/events`)).json();
}

test('the circle seats every player and shows a night or day backdrop', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3, turn_delay: 0.2 });

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('board')).toHaveAttribute('data-layout', 'player_circle');
	await expect(page.getByTestId('seat')).toHaveCount(8);
	await expect(page.getByTestId('board')).toHaveAttribute('data-theme', /night|dusk|day/);
	await expect(page.getByTestId('phase')).toHaveText(/Night|Day|Game over/);
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('after the match roles and deaths on the circle are those of the stored log', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3 });
	await finished(request, id);
	const events = await log(request, id);
	const roles = new Map<string, string>(
		events
			.filter((e: { type: string }) => e.type === 'role_assigned')
			.map((e: { data: { player: string; role: string } }) => [e.data.player, e.data.role])
	);
	const dead = events.filter((e: { type: string }) => e.type === 'player_died').length;

	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('phase')).toHaveText('Game over');
	for (const [player, role] of roles) {
		const word = role.replaceAll('_', ' ');
		await expect(
			page.locator(`[data-testid="seat"][data-seat="${player}"]`).getByTestId('role')
		).toHaveText(new RegExp(`^${word}$`, 'i'));
	}
	await expect(page.locator('.seat.dead')).toHaveCount(dead);
});

test('spoilers off turn every living role into a question mark', async ({ page, request }) => {
	const id = await start(request, { players: 6, seed: 7 });
	await finished(request, id);
	await page.goto(`/matches/${id}`);
	await expect(page.getByTestId('seat')).toHaveCount(6);
	await expect(page.getByTestId('role')).toHaveCount(6);

	await page.getByRole('link', { name: 'Spoiler-free' }).click();
	await expect(page).toHaveURL(/view=spoiler-free/);

	// Roles stay hidden, except those the game announced at a death: those are public.
	const dead = (await log(request, id)).filter(
		(e: { type: string }) => e.type === 'player_died'
	).length;
	await expect(page.getByTestId('role')).toHaveCount(0);
	await expect(page.getByTestId('revealed')).toHaveCount(dead);
	await expect(page.getByTestId('secret')).toHaveCount(6 - dead);
});

test('the votes of the day are drawn as arrows while the match is watched', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3, turn_delay: 0.3 });
	await page.goto(`/matches/${id}`);

	await expect(page.getByTestId('vote-arrow').first()).toBeAttached({ timeout: 45_000 });
	await expect(page.getByTestId('vote-count').first()).toBeVisible();
});

test('the newest speech stands on the circle, pointing at its speaker, and votes are tallied', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3 });
	await finished(request, id);
	type Logged = { type: string; visible_to: string[] | null; data: Record<string, string> };
	const events: Logged[] = await log(request, id);
	// Replay step n shows the first n events of the spectator log.
	const said = events.findIndex((e) => e.type === 'message' && e.visible_to === null);
	await page.goto(`/replays/${id}?step=${said + 1}`);
	const speech = page.getByTestId('stage-speech');
	await expect(speech).toBeVisible();
	await expect(speech).toHaveAttribute('data-seat', events[said].data.player);
	await expect(speech).toContainText(events[said].data.text);
	await expect(page.getByTestId('speech-tail')).toBeAttached();
	await expect(
		page.locator(`.seat.speaking[data-seat="${events[said].data.player}"]`)
	).toBeVisible();

	// A vote result ends the scene: no words on stage after it.
	const result = events.findIndex((e) => e.type === 'vote_result');
	await page.goto(`/replays/${id}?step=${result}`);
	await expect(page.getByTestId('tally')).toBeVisible();
	await page.goto(`/replays/${id}?step=${result + 1}`);
	await expect(page.getByTestId('stage-speech')).toHaveCount(0);
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});

test('when a scene ends the game master takes the stage until someone speaks', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3, settings: { language: 'en' } });
	await finished(request, id);
	type Logged = { type: string; visible_to: string[] | null; data: Record<string, string> };
	const events: Logged[] = await log(request, id);
	const morning = events.findIndex(
		(e) => e.type === 'narration' && String(e.data.key).startsWith('morning')
	);
	expect(morning).toBeGreaterThan(0);

	// The arena's dramatic line (analytics `narration`, #117) when it has one.
	await page.route(`**/matches/${id}/analytics*`, (route) =>
		route.fulfill({
			json: {
				game: 'werewolf',
				narration: [
					{ seq: morning, key: 'morning_deaths', text: { en: 'DRAMATIC dawn line.', de: 'x' } }
				]
			}
		})
	);
	await page.goto(`/replays/${id}?step=${morning + 1}`);
	const recap = page.getByTestId('stage-recap');
	await expect(recap).toBeVisible();
	await expect(recap).toHaveAttribute('data-key', 'morning_deaths');
	await expect(recap).toContainText('Morning');
	await expect(recap).toContainText('DRAMATIC dawn line.');
	await expect(page.getByTestId('phase')).toHaveClass(/corner/);

	// The first speech of the day takes the stage back.
	const said = events.findIndex(
		(e, i) => i > morning && e.type === 'message' && e.visible_to === null
	);
	await page.goto(`/replays/${id}?step=${said + 1}`);
	await expect(page.getByTestId('stage-speech')).toBeVisible();
	await expect(page.getByTestId('stage-recap')).toHaveCount(0);
});

test("without the arena's lines the transcript's narration stands in", async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3, settings: { language: 'en' } });
	await finished(request, id);
	type Logged = { type: string; data: Record<string, string> };
	const events: Logged[] = await log(request, id);
	const night = events.findIndex((e) => e.type === 'narration');
	// An arena without the game master's lines (before #117): no `narration` in the answer.
	await page.route(`**/matches/${id}/analytics*`, (route) => route.fulfill({ json: {} }));
	await page.goto(`/replays/${id}?step=${night + 1}`);
	await expect(page.getByTestId('stage-recap')).toBeVisible();
	await expect(page.getByTestId('stage-recap')).toContainText('Night 1 falls');
});

test('under the circle: who claims what and who suspects whom, cut at the moment on screen', async ({
	page,
	request
}) => {
	const id = await start(request, { players: 8, seed: 3, settings: { language: 'en' } });
	await finished(request, id);
	const events: { type: string }[] = await log(request, id);
	const late = events.length - 2;
	const claim = (seq: number, player: string, role: string, lie: boolean | null) => ({
		seq,
		player,
		role,
		changed_from: null,
		counterclaimed_by: [],
		disproved: false,
		true_role: null,
		lie,
		heuristic: true
	});
	await page.route(`**/matches/${id}/analytics*`, (route) =>
		route.fulfill({
			json: {
				game: 'werewolf',
				claims: [claim(20, 'p1', 'seer', false), claim(late, 'p2', 'hunter', true)],
				accusations: [
					{ seq: 21, by: 'p1', target: 'p3', source: 'speech', heuristic: true },
					{ seq: 22, by: 'p1', target: 'p3', source: 'vote' },
					{ seq: late, by: 'p4', target: 'p1', source: 'speech', heuristic: true }
				]
			}
		})
	);

	await page.goto(`/replays/${id}?step=30`);
	const intel = page.getByTestId('werewolf-intel');
	await expect(intel).toBeVisible();
	// Only what was said by the moment on screen.
	await expect(intel.getByTestId('claim')).toHaveCount(1);
	await expect(intel.getByTestId('claim')).toHaveAttribute('data-role', 'seer');
	await expect(intel.getByTestId('claim-fate')).toHaveText('true');
	const cell = intel.locator('[data-testid="suspicion-cell"][data-by="p1"][data-target="p3"]');
	await expect(cell).toHaveAttribute('title', /1 accusing sentence, 1 vote/);
	await expect(intel.getByTestId('suspicion-cell')).toHaveCount(1);
	await expect(intel.getByTestId('most-suspected')).toBeVisible();

	// At the end: the later claim, a lie, and the later accusation.
	await page.goto(`/replays/${id}`);
	await expect(intel.getByTestId('claim')).toHaveCount(2);
	await expect(intel.getByTestId('claim-fate').last()).toHaveText('a lie');
	await expect(intel.getByTestId('suspicion-cell')).toHaveCount(2);
	const overflow = await page.evaluate(
		() => document.documentElement.scrollWidth - document.documentElement.clientWidth
	);
	expect(overflow).toBeLessThanOrEqual(0);
});
