import { identity } from '../players.js';

/**
 * Pure helpers of the Throne of Tokens board (`hex_map` render_spec, docs/civ-interfaces.md):
 * where a tile sits, what its letter means, the colour of a nation and what a nation sees.
 * Tiles are `[col, row]`; odd rows sit half a tile to the right (pointy-top hexagons).
 */

export type Tile = [number, number];

export interface HexCity {
	id: string;
	owner: string;
	tile: Tile;
	population: number;
	capital: boolean;
	walls: boolean;
}

export interface HexArmy {
	id: string;
	owner: string;
	tile: Tile;
	strength: number;
	/** Spectator view only: the redaction drops the unit list. */
	units?: Record<string, number> | null;
	fortified: boolean;
}

export interface HexNation {
	id: string;
	/** Spectator view only. */
	stock?: Record<string, number> | null;
	reputation: number;
	cities: number;
	at_war: string[];
}

export interface HexSpec {
	layout: 'hex_map';
	round: number;
	rounds_total: number;
	cols: number;
	rows: number;
	terrain: string[];
	legend: Record<string, string>;
	cities: HexCity[];
	armies: HexArmy[];
	nations: HexNation[];
	treaties: { kind: string; parties: string[] }[];
	wars: [string, string][];
	/** Spectator view only: one string per row per nation, "1" = seen this round. */
	fog?: Record<string, string[]> | null;
	battles: { tile: Tile; winner: string | null }[];
}

/** Owner id of barbarians and rebel cities. */
export const NEUTRAL = 'neutral';

/** The radius of a hexagon in board units; everything else is drawn relative to it. */
export const SIZE = 10;
const WIDTH = Math.sqrt(3) * SIZE;

/** The centre of a tile in board units. */
export function centre([col, row]: Tile): { x: number; y: number } {
	return {
		x: WIDTH * (col + 0.5 + (row % 2) * 0.5),
		y: SIZE * (1 + 1.5 * row)
	};
}

/** The board's viewBox: every tile with a little margin. */
export function viewBox(cols: number, rows: number): string {
	const width = WIDTH * (cols + 0.5);
	const height = SIZE * (1.5 * rows + 0.5);
	return `-2 -2 ${round(width + 4)} ${round(height + 4)}`;
}

/** The corners of a pointy-top hexagon around a tile, as an SVG `points` value. */
export function corners(tile: Tile, size = SIZE): string {
	const { x, y } = centre(tile);
	return hexagon(x, y, size);
}

/** A pointy-top hexagon of radius `size` around a point (for the legend's swatches too). */
export function hexagon(x: number, y: number, size = SIZE): string {
	return Array.from({ length: 6 }, (_, i) => {
		const angle = (Math.PI / 180) * (60 * i - 90);
		return `${round(x + size * Math.cos(angle))},${round(y + size * Math.sin(angle))}`;
	}).join(' ');
}

const round = (n: number) => Math.round(n * 100) / 100;

/** Every tile of the map with its terrain id; a letter without a legend entry reads as "unknown". */
export function tiles(
	spec: Pick<HexSpec, 'terrain' | 'legend'>
): { tile: Tile; terrain: string }[] {
	return spec.terrain.flatMap((line, row) =>
		[...line].map((letter, col) => ({
			tile: [col, row] as Tile,
			terrain: spec.legend[letter] ?? 'unknown'
		}))
	);
}

/** Whether `nation` sees `tile` this round; without fog (spoiler-free) everything is shown. */
export function seen(fog: HexSpec['fog'], nation: string | null, [col, row]: Tile): boolean {
	if (!nation || !fog?.[nation]) return true;
	return fog[nation][row]?.[col] === '1';
}

/** The colours of the nations: each nation's player slot (lib/players.ts), neutral slate. */
export function nationColours(nations: { id: string }[]): Record<string, string> {
	const seats = nations.map((n) => n.id);
	const colours: Record<string, string> = { [NEUTRAL]: identity(NEUTRAL, seats).colour };
	for (const seat of seats) colours[seat] = identity(seat, seats).colour;
	return colours;
}

/** "iron_deposit" as "Iron deposit". */
export function terrainName(id: string): string {
	const words = id.replaceAll('_', ' ');
	return words[0].toUpperCase() + words.slice(1);
}

/** Several armies can stand on one tile (allies, a battle): each gets its own offset. */
export function spread<T extends { tile: Tile }>(items: T[]): (T & { dx: number })[] {
	const seenAt = new Map<string, number>();
	const counts = new Map<string, number>();
	for (const item of items) counts.set(String(item.tile), (counts.get(String(item.tile)) ?? 0) + 1);
	return items.map((item) => {
		const key = String(item.tile);
		const index = seenAt.get(key) ?? 0;
		seenAt.set(key, index + 1);
		const count = counts.get(key)!;
		return { ...item, dx: (index - (count - 1) / 2) * SIZE * 0.8 };
	});
}
