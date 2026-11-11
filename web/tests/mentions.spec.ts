import { expect, test } from '@playwright/test';

// Models write the seat ids they see in their prompt ("p2, two kings?"). Speech and thought
// bubbles show such a seat as its name chip; the raw switch shows the words as written.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';
const SENTENCE = 'p2, two kings with your history? I doubt it!';

test('a seat a model named in its words reads as that seat’s name chip', async ({
	page,
	request
}) => {
	const match = await (
		await request.post(`${ARENA}/matches`, {
			data: { game: 'liars_deck', players: 4, seed: 61, turn_delay: 0.5 }
		})
	).json();
	await page.route(`**/matches/${match.id}/transcript*`, async (route) => {
		const response = await route.fetch();
		const body = await response.json();
		// Lines of their own (no log position): the commentary shows them at any moment, so the
		// live playout does not hold them back.
		const line = (text: string, kind: string) => ({
			seq: null,
			kind,
			actor: 'p1',
			text: `p1: "${text}"`,
			detail: null,
			importance: 2,
			raw: { type: kind === 'thought' ? 'thought' : 'message', data: { player: 'p1', text } }
		});
		body.lines.push(line(SENTENCE, 'speech'), line('p9 is not here; p3 is.', 'thought'));
		await route.fulfill({ response, json: body });
	});

	await page.goto(`/matches/${match.id}`);

	const bubble = (kind: string, words: string) =>
		page
			.getByTestId('commentary')
			.locator(`li[data-kind="${kind}"]`)
			.filter({ hasText: words })
			.locator('.bubble');
	const speech = bubble('speech', 'two kings with your history');
	await expect(speech).toBeVisible({ timeout: 15_000 });
	const name = (await page
		.locator('[data-testid="cast"] li[data-seat="p2"] strong')
		.textContent())!.trim();
	await expect(speech.getByTestId('mention')).toHaveAttribute('data-seat', 'p2');
	// The chip carries the seat's avatar and its display name, then the model's words go on.
	await expect(speech.getByTestId('mention')).toContainText(name);
	await expect(speech).toContainText(`${name}, two kings with your history? I doubt it!`);
	await expect(speech).not.toContainText('p2,');

	// A seat that is not in the match stays as written; one that is becomes a chip.
	const thought = bubble('thought', 'p9 is not here');
	await expect(thought).toContainText('p9 is not here');
	await expect(thought.getByTestId('mention')).toHaveAttribute('data-seat', 'p3');

	// The raw switch shows the words exactly as the model wrote them.
	await page.getByTestId('raw-words').check();
	await expect(speech).toHaveText(SENTENCE);
	await expect(speech.getByTestId('mention')).toHaveCount(0);

	await request.post(`${ARENA}/matches/${match.id}/abort`);
});
