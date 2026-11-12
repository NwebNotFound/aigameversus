import { describe, expect, it } from 'vitest';
import { inline, plainText, richText } from './rich-text.js';
import { withDisplayNames } from './viewer.js';

const seats = withDisplayNames(['p1', 'p3', 'p6'], {
	p1: { name: 'gpt-luna', model: 'gpt-luna', kind: 'model' },
	p3: { name: 'mistral-small', model: 'mistral-small', kind: 'model' },
	p6: { name: 'gemini-flash-lite', model: 'gemini-flash-lite', kind: 'model' }
});

// The thought Nils saw (Werewolf, gemini-flash-lite as little_girl), exactly as stored.
const BUBBLE =
	"**Casting My Vote**\n\nI've got the game state and events, and it's daytime, specifically the voting phase. I'm playing as \"little_girl.\" Observing the current votes, I see that p1 and p3 have both voted for p6. It's time for me to make my own decision.\n\n\n**Analyzing the Voting Dynamics**\n\nI'm in the voting phase, and everyone seems to be targeting me, p6. My role as \"little_girl\" is relevant. I spied last night, but the result was inconclusive, and I wasn't caught. The other players are pressuring me for specifics, probably because I was vague. I need to make a strategic decision with my vote.";

describe('richText', () => {
	it("reads Nils' bubble: two step labels, two paragraphs, mentions as seats, no asterisks", () => {
		const blocks = richText(BUBBLE, seats);
		expect(blocks.map((b) => b.kind)).toEqual(['label', 'p', 'label', 'p']);
		expect(blocks[0]).toEqual({ kind: 'label', inline: [{ text: 'Casting My Vote' }] });
		expect(blocks[2]).toEqual({
			kind: 'label',
			inline: [{ text: 'Analyzing the Voting Dynamics' }]
		});
		const seatsIn = (b: (typeof blocks)[number]) =>
			b.kind === 'p' ? b.inline.flatMap((i) => ('seat' in i ? [i.seat] : [])) : [];
		expect(seatsIn(blocks[1])).toEqual(['p1', 'p3', 'p6']);
		expect(seatsIn(blocks[3])).toEqual(['p6']);
		expect(JSON.stringify(blocks)).not.toContain('**');
	});

	it('keeps mentions working inside bold and italic', () => {
		expect(inline('**p3 lies** and *p1 knows*', seats)).toEqual([
			{ bold: [{ seat: 'p3', text: 'p3' }, { text: ' lies' }] },
			{ text: ' and ' },
			{ italic: [{ seat: 'p1', text: 'p1' }, { text: ' knows' }] }
		]);
	});

	it('reads lists and keeps line breaks inside a paragraph', () => {
		expect(richText('- p1 voted\n- p3 too', seats)).toEqual([
			{
				kind: 'list',
				items: [
					[{ seat: 'p1', text: 'p1' }, { text: ' voted' }],
					[{ seat: 'p3', text: 'p3' }, { text: ' too' }]
				]
			}
		]);
		expect(richText('one\ntwo')).toEqual([
			{ kind: 'p', inline: [{ text: 'one' }, { br: true }, { text: 'two' }] }
		]);
	});

	it('never turns text into markup: HTML and links stay characters, unclosed markers stay', () => {
		const blocks = richText(
			'<script>alert(1)</script> [x](javascript:alert(1)) 2*3 = 6 and **open'
		);
		expect(blocks).toEqual([
			{
				kind: 'p',
				inline: [{ text: '<script>alert(1)</script> [x](javascript:alert(1)) 2*3 = 6 and **open' }]
			}
		]);
	});
});

describe('plainText', () => {
	it('strips the markup for one-line places', () => {
		expect(plainText(BUBBLE).startsWith("Casting My Vote I've got the game state")).toBe(true);
		expect(plainText('- **p3** is *odd*')).toBe('p3 is odd');
	});
});
