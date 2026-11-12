import { expect, rewrite, test } from './routes.js';

// A model's refused answer is answer quality, not an error on screen: the move that counted
// carries a small "retry" marker, the refused attempt's thought and the refusal line show only
// with "Show bookkeeping". Red is kept for a move the engine played at random.

const ARENA = process.env.ARENA_URL ?? 'http://127.0.0.1:8100';

test('refused answers fold into a retry marker; only a random move is red', async ({
	page,
	request
}) => {
	const match = await (
		await request.post(`${ARENA}/matches`, {
			data: { game: 'liars_deck', players: 4, seed: 62, turn_delay: 0.5 }
		})
	).json();
	await rewrite(page, `**/matches/${match.id}/transcript*`, (body) => {
		// Lines of their own (no log position), so the live playout shows them at once.
		const line = (actor: string, kind: string, type: string, text: string, importance = 2) => ({
			seq: null,
			kind,
			actor,
			text,
			detail: null,
			importance,
			raw: { type, data: { player: actor, text } }
		});
		body.lines.push(
			// The shape of gpt-luna's flop check: refused once, fixed on the retry.
			line('p1', 'thought', 'thought', 'A first try that went wrong.'),
			line('p1', 'info', 'action_rejected', "p1's move was refused: bad arguments"),
			line('p1', 'thought', 'thought', 'The thinking that counted.'),
			line('p1', 'info', 'action_accepted', 'p1 chooses play', 1),
			line('p1', 'action', 'cards_played', 'MARKER-RETRY p1 plays two cards'),
			// No usable answer at all: the engine plays a random move.
			line('p2', 'info', 'action_rejected', "p2's move was refused: no tool call"),
			line('p2', 'info', 'action_fallback', 'No usable move from p2: a random move is played'),
			line('p2', 'action', 'cards_played', 'MARKER-RANDOM p2 plays one card')
		);
	});

	await page.goto(`/matches/${match.id}`);
	const feed = page.getByTestId('commentary');
	const move = feed.locator('li').filter({ hasText: 'MARKER-RETRY' });
	await expect(move).toBeVisible({ timeout: 15_000 });

	const mark = move.getByTestId('retry-mark');
	await expect(mark).toHaveText('retry');
	await expect(mark).toHaveAttribute('title', /first answer was malformed, fixed on retry/);
	// The refused attempt and its thought stay out of the default feed.
	await expect(feed).not.toContainText('A first try that went wrong');
	await expect(feed).not.toContainText('was refused');
	await expect(feed).toContainText('The thinking that counted');

	// The engine's random move is the one red marker.
	const random = feed
		.locator('li')
		.filter({ hasText: 'MARKER-RANDOM' })
		.getByTestId('fallback-mark');
	await expect(random).toHaveText('random move');
	await expect(random).toHaveAttribute('title', /random move/);
	// The retry marker is muted, not the error colour of the random move.
	const colour = (el: Element) => getComputedStyle(el).color;
	expect(await mark.evaluate(colour)).not.toBe(await random.evaluate(colour));

	// "Show bookkeeping" shows the raw lines, the refused thought included.
	await page.getByText('Show bookkeeping').click();
	await expect(feed).toContainText('A first try that went wrong');
	await expect(feed).toContainText('was refused: bad arguments');

	await request.post(`${ARENA}/matches/${match.id}/abort`);
});
