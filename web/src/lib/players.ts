/**
 * One identity per player, everywhere (docs/UI-DESIGN.md, design review 3.2): a seat's slot
 * gives its colour, its shape and its line dash, so a map token, a chart line, a legend and
 * a name read as the same player, and colour is never the only cue. Slots follow seat order
 * within a match (p1 is slot 1). Up to six players get a colour; a game with more seats
 * (Werewolf) uses numbered neutral marks instead (`coloured: false`).
 */

export type Shape = 'circle' | 'diamond' | 'triangle' | 'square' | 'pentagon' | 'star' | 'cross';

export interface Identity {
	/** 1 to 6, or 0 for neutral. */
	slot: number;
	/** A CSS colour: the slot's token, so it follows the theme. */
	colour: string;
	shape: Shape;
	/** SVG stroke-dasharray for chart lines; '' is solid. */
	dash: string;
	coloured: boolean;
}

const SLOTS: Omit<Identity, 'slot' | 'coloured'>[] = [
	{ colour: 'var(--p1)', shape: 'circle', dash: '' },
	{ colour: 'var(--p2)', shape: 'diamond', dash: '8 4' },
	{ colour: 'var(--p3)', shape: 'triangle', dash: '2 3' },
	{ colour: 'var(--p4)', shape: 'square', dash: '8 3 2 3' },
	{ colour: 'var(--p5)', shape: 'pentagon', dash: '4 3' },
	{ colour: 'var(--p6)', shape: 'star', dash: '8 3 2 3 2 3' }
];

export const NEUTRAL: Identity = {
	slot: 0,
	colour: 'var(--p-neutral)',
	shape: 'cross',
	dash: '1 0',
	coloured: false
};

/** Owner ids that are no player: barbarians, rebel cities. */
const NEUTRAL_IDS = new Set(['neutral', 'barbarians']);

/**
 * The identity of `seat` among `seats` (the match's seat order). A neutral owner, a seat
 * not in the match, or a table of more than six seats is neutral.
 */
export function identity(seat: string, seats: string[]): Identity {
	if (NEUTRAL_IDS.has(seat)) return NEUTRAL;
	const index = seats.indexOf(seat);
	if (index < 0 || seats.length > SLOTS.length) return NEUTRAL;
	return { slot: index + 1, coloured: true, ...SLOTS[index] };
}

/** Every seat's identity, for components that draw many players at once. */
export function identities(seats: string[]): Record<string, Identity> {
	return Object.fromEntries(seats.map((seat) => [seat, identity(seat, seats)]));
}

/**
 * The outline of a shape centred on 0,0 with radius `r`, as an SVG path. Shapes share an
 * optical size: the area of each is close to that of the circle.
 */
export function shapePath(shape: Shape, r: number): string {
	const at = (count: number, turn: number, radius: number) =>
		Array.from({ length: count }, (_, i) => {
			const a = ((i * 2 * Math.PI) / count + turn) % (2 * Math.PI);
			return `${round(radius * Math.sin(a))},${round(-radius * Math.cos(a))}`;
		});
	const polygon = (points: string[]) => `M${points.join('L')}Z`;
	switch (shape) {
		case 'circle':
			return `M${-r},0a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0Z`;
		case 'diamond':
			return polygon(at(4, 0, r * 1.18));
		case 'triangle':
			return polygon(at(3, 0, r * 1.3));
		case 'square': {
			const h = round(r * 0.88);
			return `M${-h},${-h}H${h}V${h}H${-h}Z`;
		}
		case 'pentagon':
			return polygon(at(5, 0, r * 1.08));
		case 'star': {
			const outer = at(5, 0, r * 1.25);
			const inner = at(5, Math.PI / 5, r * 0.55);
			return polygon(outer.flatMap((p, i) => [p, inner[i]]));
		}
		case 'cross': {
			const w = round(r * 0.36);
			const l = round(r);
			return `M${-w},${-l}H${w}V${-w}H${l}V${w}H${w}V${l}H${-w}V${w}H${-l}V${-w}H${-w}Z`;
		}
	}
}

const round = (n: number) => Math.round(n * 100) / 100;
