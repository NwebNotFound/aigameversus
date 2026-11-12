import { describe, expect, it } from 'vitest';
import fixture from './fixture-hex-map.json';
import {
	NEUTRAL,
	SIZE,
	centre,
	corners,
	nationColours,
	seen,
	spread,
	terrainName,
	tiles,
	viewBox,
	type HexSpec,
	type Tile
} from './hexMap.js';

const spec = fixture as unknown as HexSpec;

describe('centre', () => {
	it('shifts odd rows half a tile to the right, as the map generator does', () => {
		const w = Math.sqrt(3) * SIZE;
		expect(centre([0, 0]).x).toBeCloseTo(w / 2);
		expect(centre([0, 1]).x).toBeCloseTo(w);
		expect(centre([1, 0]).x - centre([0, 0]).x).toBeCloseTo(w);
		expect(centre([0, 1]).y - centre([0, 0]).y).toBeCloseTo(1.5 * SIZE);
	});

	it('neighbours touch: the step to a neighbour is one tile width', () => {
		const a = centre([2, 2]);
		const b = centre([2, 3]); // the lower right neighbour of an even row
		expect(Math.hypot(b.x - a.x, b.y - a.y)).toBeCloseTo(Math.sqrt(3) * SIZE);
	});
});

describe('the map of the fixture (made by the real generator)', () => {
	it('has a terrain for every tile', () => {
		const all = tiles(spec);
		expect(all).toHaveLength(spec.cols * spec.rows);
		expect(all.every((t) => t.terrain !== 'unknown')).toBe(true);
	});

	it('fits every hexagon into the viewBox', () => {
		const [x, y, w, h] = viewBox(spec.cols, spec.rows).split(' ').map(Number);
		for (const { tile } of tiles(spec))
			for (const point of corners(tile).split(' ')) {
				const [px, py] = point.split(',').map(Number);
				expect(px).toBeGreaterThanOrEqual(x);
				expect(py).toBeGreaterThanOrEqual(y);
				expect(px).toBeLessThanOrEqual(x + w);
				expect(py).toBeLessThanOrEqual(y + h);
			}
	});
});

describe('seen', () => {
	it("reads a nation's fog row, and shows everything without fog", () => {
		const fog = { p1: ['10', '01'] };
		expect(seen(fog, 'p1', [0, 0])).toBe(true);
		expect(seen(fog, 'p1', [1, 0])).toBe(false);
		expect(seen(fog, 'p1', [1, 1])).toBe(true);
		expect(seen(null, 'p1', [1, 0])).toBe(true);
		expect(seen(fog, null, [1, 0])).toBe(true);
	});
});

describe('nationColours', () => {
	it('gives each nation its own colour and the neutrals slate', () => {
		const colours = nationColours(spec.nations);
		expect(new Set(spec.nations.map((n) => colours[n.id])).size).toBe(spec.nations.length);
		expect(colours[NEUTRAL]).toBeDefined();
	});
});

describe('spread', () => {
	it('sets armies on one tile side by side, a lone one in the middle', () => {
		const t: Tile = [1, 1];
		const [a, b, c] = spread([{ tile: t }, { tile: t }, { tile: [2, 2] as Tile }]);
		expect(a.dx).toBeCloseTo(-b.dx);
		expect(c.dx).toBe(0);
	});
});

it('names terrain ids', () => {
	expect(terrainName('iron_deposit')).toBe('Iron deposit');
});
