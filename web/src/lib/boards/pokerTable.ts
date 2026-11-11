/** Pure helpers of the Poker table: seat positions, card faces, chip stacks, percentages. */

export interface Point {
	/** Percent of the table's width and height. */
	left: number;
	top: number;
}

/**
 * Where seat `index` of `count` sits on the oval, the first seat at the bottom and the
 * others clockwise. Percent of the table's box, the middle of the seat.
 */
export function seatPoint(index: number, count: number): Point {
	const angle = Math.PI / 2 + (index / count) * 2 * Math.PI;
	return {
		left: Math.round((50 + 40 * Math.cos(angle)) * 10) / 10,
		top: Math.round((50 + 37 * Math.sin(angle)) * 10) / 10
	};
}

const SUITS: Record<string, { symbol: string; name: string; red: boolean }> = {
	c: { symbol: '♣', name: 'clubs', red: false },
	d: { symbol: '♦', name: 'diamonds', red: true },
	h: { symbol: '♥', name: 'hearts', red: true },
	s: { symbol: '♠', name: 'spades', red: false }
};

export interface PokerCard {
	rank: string;
	symbol: string;
	red: boolean;
	/** For screen readers, e.g. "A of hearts". */
	label: string;
}

/** A card such as "Ah" or "Td" (ten shows as 10). Null if it is not a card. */
export function card(text: string): PokerCard | null {
	const suit = SUITS[text[1]];
	if (text.length !== 2 || !suit || !'23456789TJQKA'.includes(text[0])) return null;
	const rank = text[0] === 'T' ? '10' : text[0];
	return { rank, symbol: suit.symbol, red: suit.red, label: `${rank} of ${suit.name}` };
}

/** How many coins a stack is drawn with: 1 for a small stack, at most 5 for a big one. */
export function coins(stack: number): number {
	if (stack <= 0) return 0;
	return Math.min(5, 1 + Math.floor(Math.log10(Math.max(1, stack / 10))));
}

/** A chance from 0 to 1 as a whole percent, "–" when there is none. */
export function percent(chance: number | null | undefined): string {
	return typeof chance === 'number' ? `${Math.round(chance * 100)}%` : '–';
}

const POSITIONS: Record<string, string> = {
	button: 'D',
	small_blind: 'SB',
	big_blind: 'BB'
};

/** The short tag of a table position; nothing for the others. */
export function positionTag(position: unknown): string | null {
	return typeof position === 'string' ? (POSITIONS[position] ?? null) : null;
}
