import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

// Spoiler-free pages: nothing hidden reaches the browser, in any response the page gets.
// Bot matches of every game with a board; REAL_MATCH_IDS (comma-separated) adds stored
// matches played by models, whose thoughts and whispers are checked as well.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

interface Event {
	seq: number;
	type: string;
	data: Record<string, unknown>;
	visible_to: string[] | null;
}

// Events the engine logs for spectators only that every player's view still tells.
const ALWAYS_SHOWN = new Set([
	'match_started',
	'match_paused',
	'match_resumed',
	'turn_limit_reached'
]);

async function finished(request: APIRequestContext, body: Record<string, unknown>) {
	const match = await (await request.post(`${ARENA}/matches`, { data: body })).json();
	await expect
		.poll(async () => (await (await request.get(`${ARENA}/matches/${match.id}`)).json()).status, {
			timeout: 60_000
		})
		.toBe('finished');
	return match.id as string;
}

/** What must never be in a spoiler-free response: hidden event types and hidden words. */
async function secretsOf(request: APIRequestContext, id: string) {
	const log: Event[] = await (await request.get(`${ARENA}/matches/${id}/events`)).json();
	const publicTypes = new Set(log.filter((e) => e.visible_to === null).map((e) => e.type));
	const types = new Set(
		log
			.filter((e) => e.visible_to !== null && !ALWAYS_SHOWN.has(e.type) && !publicTypes.has(e.type))
			.map((e) => e.type)
	);
	// Thoughts and whispers: the words themselves, long enough to be unique.
	const words = log
		.filter((e) => e.visible_to !== null && typeof e.data.text === 'string')
		.map((e) => String(e.data.text).slice(0, 60))
		.filter((text) => text.length >= 12);
	return { types: [...types].map((t) => `"${t}"`), words };
}

/** Resolve SvelteKit's flattened page data (devalue) into plain values. */
function unflatten(values: unknown[]): unknown {
	const seen = new Map<number, unknown>();
	const at = (index: number): unknown => {
		if (index < 0) return null;
		if (seen.has(index)) return seen.get(index);
		const value = values[index];
		if (Array.isArray(value)) {
			const out: unknown[] = [];
			seen.set(index, out);
			for (const item of value) out.push(at(item as number));
			return out;
		}
		if (value && typeof value === 'object') {
			const out: Record<string, unknown> = {};
			seen.set(index, out);
			for (const [key, item] of Object.entries(value)) out[key] = at(item as number);
			return out;
		}
		return value;
	};
	return at(0);
}

/**
 * Every hand and hole card is a placeholder, every role empty, no win chance or seed, and
 * every event public. Event data (`.data`) is what the event says in the open, for example
 * the cards a call revealed, so it is not held to the board's rules.
 */
function expectRedacted(value: unknown, path = '') {
	if (Array.isArray(value)) return value.forEach((v, i) => expectRedacted(v, `${path}[${i}]`));
	if (!value || typeof value !== 'object') return;
	// Under an event's own data, at any depth: the events list and a transcript line's raw event.
	const inEventData = /(\.events\.data\[\d+\]|\.raw)\.data(\.|\[|$)/.test(path);
	for (const [key, inner] of Object.entries(value)) {
		const where = `${path}.${key}`;
		expect(key, where).not.toBe('win_probability');
		if (key === 'seed') expect(inner, where).toBeNull();
		if (!inEventData && key === 'role') expect(inner, where).toBeNull();
		if (!inEventData && (key === 'hand' || key === 'cards') && Array.isArray(inner)) {
			for (const card of inner) expect(String(card), where).toMatch(/^hidden-\d+$/);
		}
		if (key === 'visible_to' && /\.events\.data\[\d+\]$/.test(path))
			expect(inner, where).toBeNull();
		expectRedacted(inner, where);
	}
}

/** Collect the body of every response the page receives. */
function recordBodies(page: Page): string[] {
	const bodies: string[] = [];
	page.on('response', async (response) => {
		const type = response.headers()['content-type'] ?? '';
		if (!/html|json|event-stream/.test(type)) return;
		try {
			bodies.push(await response.text());
		} catch {
			// Redirects and aborted requests have no body.
		}
	});
	return bodies;
}

async function check(page: Page, request: APIRequestContext, id: string, path: string) {
	const { types, words } = await secretsOf(request, id);
	const bodies = recordBodies(page);

	await page.goto(`${path}?view=spoiler-free`);
	await expect(page.getByRole('link', { name: 'Spoiler-free' })).toHaveAttribute(
		'aria-current',
		'true'
	);
	if (path.startsWith('/replays')) {
		// Step through, so the board of several moments is fetched.
		await page.getByRole('button', { name: 'To the start' }).click();
		for (let i = 0; i < 6; i++) await page.getByRole('button', { name: 'Next moment' }).click();
		await page.getByRole('button', { name: 'To the end' }).click();
	} else {
		await expect(page.getByTestId('connection')).toHaveText('whole log loaded');
	}
	await page.waitForLoadState('networkidle');

	// Nothing on screen that only spectators may see.
	await expect(page.locator('[data-kind="thought"], [data-kind="whisper"]')).toHaveCount(0);
	await expect(page.getByTestId('tab-thoughts')).toHaveCount(0);
	await expect(page.getByTestId('export')).toHaveCount(0);
	await expect(page.getByTestId('seed')).toHaveCount(0);

	// Nothing hidden in any response body: page, data, transcript, boards and stream.
	const all = bodies.join('\n');
	expect(all.length).toBeGreaterThan(1000);
	for (const type of types) expect(all, `event type ${type}`).not.toContain(type);
	for (const text of words) expect(all, 'a thought or whisper').not.toContain(text);
	expect(all).not.toMatch(/"seed":\s*\d/);
	expect(all).not.toContain('win_probability');
	for (const body of bodies.filter((b) => b.startsWith('{"game"'))) {
		expectRedacted(JSON.parse(body).spec);
	}

	// The data the page was loaded with, as a client-side navigation would get it.
	const data = await (await request.get(`${path}/__data.json?view=spoiler-free`)).json();
	for (const node of data.nodes) if (node?.data) expectRedacted(unflatten(node.data));
}

for (const [game, players] of [
	['liars_deck', 4],
	['poker', 4],
	['werewolf', 8]
] as const) {
	test(`a spoiler-free ${game} replay and live page get no hidden data`, async ({
		page,
		request
	}) => {
		const id = await finished(request, { game, players, seed: 17 });
		await check(page, request, id, `/replays/${id}`);
		await check(page, request, id, `/matches/${id}`);
	});
}

for (const id of (process.env.REAL_MATCH_IDS ?? '').split(',').filter(Boolean)) {
	test(`the stored model match ${id.slice(0, 8)} stays spoiler-free`, async ({ page, request }) => {
		await check(page, request, id, `/replays/${id}`);
	});
}

test('spectator view shows thoughts, the seed and the export', async ({ page, request }) => {
	const id = await finished(request, { game: 'liars_deck', players: 3, seed: 18 });
	await page.goto(`/replays/${id}`);
	await page.getByLabel('More').click();
	await expect(page.getByTestId('export')).toBeVisible();
	await expect(page.getByTestId('seed')).toHaveText('Seed 18');
	await expect(page.getByTestId('tab-thoughts')).toBeVisible();
});

test('switching the view keeps the moment and loads the other data', async ({ page, request }) => {
	const id = await finished(request, { game: 'werewolf', players: 8, seed: 19 });
	const log: Event[] = await (await request.get(`${ARENA}/matches/${id}/events`)).json();
	const publicCount = log.filter((e) => e.visible_to === null).length;

	await page.goto(`/replays/${id}`);
	await expect(page.getByTestId('position')).toHaveText(`Step ${log.length} of ${log.length}`);

	await page.getByRole('link', { name: 'Spoiler-free' }).click();
	await expect(page).toHaveURL(/view=spoiler-free/);
	await expect(page.getByTestId('position')).toHaveText(`Step ${publicCount} of ${publicCount}`);
	await expect(page.getByTestId('secret').first()).toBeVisible();

	await page.getByRole('link', { name: 'Spectator' }).click();
	await expect(page).not.toHaveURL(/view=/);
	await expect(page.getByTestId('position')).toHaveText(`Step ${log.length} of ${log.length}`);
	await expect(page.getByTestId('secret')).toHaveCount(0);
});

test('with reduced motion nothing on the watch screen animates', async ({ page, request }) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	const id = await finished(request, { game: 'liars_deck', players: 3, seed: 20 });
	await page.goto(`/replays/${id}?step=0`);
	for (let i = 0; i < 8; i++) await page.getByRole('button', { name: 'Next moment' }).click();

	const running = await page.evaluate(
		() => document.getAnimations().filter((a) => a.playState === 'running').length
	);
	expect(running).toBe(0);
});
