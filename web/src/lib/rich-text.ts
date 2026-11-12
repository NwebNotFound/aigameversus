/**
 * The little markup models put in their words, read safely: **bold**, *italic*, "- " lists,
 * paragraphs and line breaks, and seat mentions ("p4") inside all of them. The result is a
 * plain tree that components draw element by element; nothing is ever parsed as HTML, so a
 * model can write "<script>" or "[x](javascript:…)" and it shows as those characters.
 */
import type { Seat } from './api.js';
import { mentionParts } from './viewer.js';

export type Inline =
	| { text: string }
	| { seat: string; text: string }
	| { bold: Inline[] }
	| { italic: Inline[] }
	| { br: true };

export type Block =
	/** A paragraph that is only bold text: a reasoning step's heading ("**Casting My Vote**"). */
	| { kind: 'label'; inline: Inline[] }
	| { kind: 'p'; inline: Inline[] }
	| { kind: 'list'; items: Inline[][] };

/** Text with its seat mentions, as inline pieces. */
function mentions(text: string, players: Record<string, Seat> | undefined): Inline[] {
	return mentionParts(text, players).map((part) =>
		'seat' in part ? { seat: part.seat, text: part.text } : { text: part.text }
	);
}

/**
 * **bold** and *italic* (also __bold__ and _italic_ at word edges), with mentions inside.
 * An unclosed marker stays as the characters it is.
 */
export function inline(text: string, players?: Record<string, Seat>): Inline[] {
	const out: Inline[] = [];
	const pattern =
		/\*\*(.+?)\*\*|__(.+?)__|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)/g;
	let last = 0;
	for (const match of text.matchAll(pattern)) {
		if (match.index > last) out.push(...mentions(text.slice(last, match.index), players));
		const bold = match[1] ?? match[2];
		if (bold !== undefined) out.push({ bold: inline(bold, players) });
		else out.push({ italic: inline(match[3] ?? match[4], players) });
		last = match.index + match[0].length;
	}
	if (last < text.length) out.push(...mentions(text.slice(last), players));
	return out;
}

function withBreaks(lines: string[], players?: Record<string, Seat>): Inline[] {
	return lines.flatMap((line, i) => [
		...(i ? [{ br: true } as const] : []),
		...inline(line, players)
	]);
}

/** A model's words as blocks: labels, paragraphs and lists. */
export function richText(text: string, players?: Record<string, Seat>): Block[] {
	const blocks: Block[] = [];
	for (const chunk of text.replace(/\r\n?/g, '\n').split(/\n\s*\n/)) {
		const lines = chunk.split('\n').filter((l) => l.trim() !== '');
		if (lines.length === 0) continue;
		if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
			blocks.push({
				kind: 'list',
				items: lines.map((l) => inline(l.replace(/^\s*[-*•]\s+/, ''), players))
			});
			continue;
		}
		const only = lines.length === 1 && lines[0].trim().match(/^\*\*([^*]+)\*\*:?$/);
		if (only) blocks.push({ kind: 'label', inline: inline(only[1], players) });
		else blocks.push({ kind: 'p', inline: withBreaks(lines, players) });
	}
	return blocks;
}

/** The words without the markup, for one-line places (a card's "last thought"). */
export function plainText(text: string): string {
	return text
		.replace(/\*\*(.+?)\*\*|__(.+?)__/g, '$1$2')
		.replace(/(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])/g, '$1')
		.replace(/^\s*[-*•]\s+/gm, '')
		.replace(/\s+/g, ' ')
		.trim();
}
