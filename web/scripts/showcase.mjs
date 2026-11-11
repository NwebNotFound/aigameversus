// Records the README material against a running stack: frames for the GIFs and 1280 px
// screenshots. It starts bot matches (no model, no cost) and only looks at public pages.
// Run through scripts/make_showcase.sh; environment: WEB_URL, ARENA_URL, FRAMES, OUT.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { chromium } from '@playwright/test';

const WEB = process.env.WEB_URL ?? 'http://127.0.0.1:3100';
const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';
const FRAMES = process.env.FRAMES ?? '.showcase-frames';
const OUT = process.env.OUT ?? '../docs/images';
mkdirSync(OUT, { recursive: true });

const api = async (path, init) => {
	const response = await fetch(`${ARENA}${path}`, init);
	if (!response.ok) throw new Error(`${path}: ${response.status} ${await response.text()}`);
	return response.json();
};
const start = (body) =>
	api('/matches', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function finished(id) {
	for (let i = 0; i < 240; i++) {
		if ((await api(`/matches/${id}`)).status === 'finished') return;
		await sleep(500);
	}
	throw new Error(`match ${id} did not finish`);
}

/** Screenshots of the viewport for `seconds`, as numbered PNGs with their real durations. */
async function record(page, name, seconds) {
	const dir = join(FRAMES, name);
	mkdirSync(dir, { recursive: true });
	const durations = [];
	const began = Date.now();
	let last = began;
	for (let n = 0; Date.now() - began < seconds * 1000; n++) {
		await page.screenshot({ path: join(dir, `${String(n).padStart(4, '0')}.png`) });
		const now = Date.now();
		durations.push(now - last);
		last = now;
	}
	durations[0] = durations[1] ?? 200;
	writeFileSync(join(dir, 'durations.json'), JSON.stringify(durations));
	console.log(`${name}: ${durations.length} frames`);
}

// 1. Matches for the leaderboard, the profile and the replay: all random bots.
const seeded = [];
for (const [game, players, seed] of [
	['liars_deck', 4, 11],
	['liars_deck', 3, 12],
	['liars_deck', 4, 13],
	['poker', 4, 21],
	['poker', 3, 22],
	['werewolf', 8, 31],
	['werewolf', 8, 32],
	['werewolf', 10, 33]
]) {
	const match = await start({ game, players, seed });
	seeded.push(match.id);
}
await Promise.all(seeded.map(finished));
const replayId = seeded[0];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1100, height: 720 } });
const page = await context.newPage();

// 2. GIFs of the live view: a match played slowly enough to follow.
for (const [name, body, wait, seconds] of [
	['liars-deck', { game: 'liars_deck', players: 4, seed: 5, turn_delay: 0.7 }, 2500, 11],
	['poker', { game: 'poker', players: 4, seed: 4, turn_delay: 0.45 }, 2500, 11],
	['werewolf', { game: 'werewolf', players: 8, seed: 3, turn_delay: 0.6 }, 800, 11]
]) {
	const match = await start(body);
	await page.goto(`${WEB}/matches/${match.id}`);
	await page.getByTestId('board').waitFor();
	await sleep(wait);
	await record(page, name, seconds);
	// A match that already ended answers 409; that is fine.
	await api(`/matches/${match.id}/abort`, { method: 'POST' }).catch(() => {});
}

// 3. The hero GIF: a replay played forward, board and both columns following.
await page.goto(`${WEB}/replays/${replayId}?step=0`);
await page.getByTestId('position').waitFor();
await page.getByLabel('Speed').selectOption({ label: '4×' });
await page.getByRole('button', { name: 'Play' }).click();
await record(page, 'hero', 10);

// 4. Screenshots at 1280 px.
const wide = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const shot = await wide.newPage();
const top = (await api('/leaderboard')).rows[0];
await shot.goto(`${WEB}/leaderboard`);
await shot.getByTestId('leaderboard').waitFor();
await shot.screenshot({ path: join(OUT, 'showcase-leaderboard.png') });
await shot.goto(`${WEB}/profiles/${top.profile_id}`);
await shot.getByTestId('game-stats').first().waitFor();
await shot.screenshot({ path: join(OUT, 'showcase-profile.png'), fullPage: true });
await shot.goto(`${WEB}/replays/${replayId}?tab=chronicle&step=0`);
await shot.getByTestId('chronicle-story').waitFor();
await shot.screenshot({ path: join(OUT, 'showcase-chronicle.png') });
await browser.close();
console.log('screenshots written to', OUT);
