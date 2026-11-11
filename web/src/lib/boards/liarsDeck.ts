/** Pure helpers of the Liar's Deck table: seating, card faces and the moments worth a pause. */
import type { MatchEvent } from '../api.js';

export type Side = 'bottom' | 'left' | 'top' | 'right';

/** Where the seats of a table of 2 to 4 sit, the first seat at the bottom. */
export function sides(count: number): Side[] {
	if (count <= 2) return ['bottom', 'top'].slice(0, count) as Side[];
	if (count === 3) return ['bottom', 'left', 'right'];
	return ['bottom', 'left', 'top', 'right'];
}

const RANK_NAMES: Record<string, string> = {
	K: 'King',
	Q: 'Queen',
	A: 'Ace',
	J: 'Joker',
	D: 'Joker'
};

export interface CardFace {
	id: string;
	/** The big letter on the card. */
	mark: string;
	/** The small number that tells two cards of a rank apart. */
	index: string;
	/** For screen readers, e.g. "King 3". */
	label: string;
	joker: boolean;
	devil: boolean;
}

/** A card id such as "K3", "J1" or "DV" (the devil card, a joker) as a face. */
export function face(id: string): CardFace {
	const devil = id === 'DV';
	const joker = devil || id.startsWith('J');
	const name = RANK_NAMES[id[0]] ?? id;
	return {
		id,
		mark: devil ? '☠' : joker ? '★' : id[0],
		index: devil ? '' : id.slice(1),
		label: devil ? 'Devil card' : `${name} ${id.slice(1)}`.trim(),
		joker,
		devil
	};
}

/** The table card as a word for the middle of the table: "queen" becomes "Queen". */
export function tableCardName(card: unknown): string {
	return typeof card === 'string' && card ? card[0].toUpperCase() + card.slice(1) : '–';
}

export interface Moment {
	/** The log position it comes from, so one moment is shown once. */
	seq: number;
	kind: 'liar' | 'shot';
	/** The words on the banner. */
	text: string;
	/** For a shot: whether the chamber was live. */
	live?: boolean;
}

/** The dramatic moments in `events` after position `after`, oldest first. */
export function moments(events: MatchEvent[], after: number): Moment[] {
	const found: Moment[] = [];
	for (const event of events) {
		if (event.seq <= after) continue;
		const { data } = event;
		if (event.type === 'liar_called') {
			const who = data.automatic ? 'forced to call' : 'calls';
			found.push({ seq: event.seq, kind: 'liar', text: `${data.caller} ${who}: Liar!` });
		} else if (event.type === 'trigger_pulled') {
			const live = data.live === true;
			found.push({
				seq: event.seq,
				kind: 'shot',
				live,
				text: live ? `${data.player}: BANG` : `${data.player}: click`
			});
		}
	}
	return found;
}
