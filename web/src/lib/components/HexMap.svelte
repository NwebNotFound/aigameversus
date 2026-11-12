<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		NEUTRAL,
		SIZE,
		centre,
		corners,
		hexagon,
		nationColours,
		seen,
		spread,
		terrainName,
		tiles,
		viewBox,
		type HexSpec
	} from '#lib/boards/hexMap.js';

	/**
	 * The Throne of Tokens board: the hex map with its terrain, cities, armies and this
	 * round's battles, the nations beside it, and the map as one nation sees it: a lens in
	 * the spectator view; in the spoiler-free view the only map there is, filtered on the
	 * server (`?nation=`, hexNationView). Every mark is drawn here in SVG.
	 */
	let {
		spec,
		names = {},
		spoilers = true
	}: {
		spec: HexSpec;
		names?: Record<string, string>;
		/** Spectator view: the whole map, with a fog lens. Spoiler-free: one nation's map. */
		spoilers?: boolean;
	} = $props();

	const colours = $derived(nationColours(spec.nations));
	const name = (id: string) => (id === NEUTRAL ? 'Neutral' : (names[id] ?? id));
	const all = $derived(tiles(spec));
	const armies = $derived(spread(spec.armies));
	const hasFog = $derived(!!spec.fog && Object.keys(spec.fog).length > 0);
	/** Whose eyes the map is seen through; null for everything (the spectator's map). */
	let eyes = $state<string | null>(null);
	/** Spoiler-free: the nation the server filtered the map for (its fog row is the only one). */
	const through = $derived(spoilers ? null : (Object.keys(spec.fog ?? {})[0] ?? null));
	const lens = $derived(spoilers ? eyes : through);
	const visible = (tile: [number, number]) => seen(spec.fog, lens, tile);
	/** Another nation's eyes in the spoiler-free view: the server sends that nation's map. */
	function seeAs(nation: string) {
		const url = new URL(page.url.href);
		url.searchParams.set('nation', nation);
		// The page's load reads `?nation=`, so it reruns and brings that nation's map.
		goto(url, { replace: true, reset: false });
	}
	const capitals = $derived(
		Object.fromEntries(spec.cities.filter((c) => c.capital).map((c) => [c.owner, c.tile]))
	);
	const fronts = $derived(
		spec.wars
			.map(([a, b]) =>
				capitals[a] && capitals[b]
					? { a, b, from: centre(capitals[a]), to: centre(capitals[b]) }
					: null
			)
			.filter((f) => f !== null)
	);
	const progress = $derived(spec.rounds_total ? spec.round / spec.rounds_total : 0);
	const legendTerrains = $derived([...new Set(all.map((t) => t.terrain))]);
</script>

{#snippet glyph(terrain: string, x: number, y: number)}
	{@const s = SIZE / 10}
	<g class="glyph {terrain}" transform="translate({x} {y}) scale({s})" aria-hidden="true">
		{#if terrain === 'forest'}
			<path d="M-4 3 L-2 -2 L0 3 Z M0 3 L2.5 -3.5 L5 3 Z" />
		{:else if terrain === 'hills'}
			<path d="M-5 3 Q-2.5 -2 0 3 M-1 3 Q2 -3 5 3" />
		{:else if terrain === 'mountains'}
			<path d="M-5.5 4 L-1.5 -4 L2.5 4 Z M0.5 4 L3.5 -1.5 L6 4 Z" />
			<path class="snow" d="M-2.9 -1.2 L-1.5 -4 L-0.1 -1.2 Z" />
		{:else if terrain === 'water'}
			<path
				d="M-5 -1 q1.25 -1.5 2.5 0 t2.5 0 t2.5 0 t2.5 0 M-5 2.5 q1.25 -1.5 2.5 0 t2.5 0 t2.5 0 t2.5 0"
			/>
		{:else if terrain === 'river'}
			<path d="M-7 -3 C-3 -3 -3 3 1 3 S5 -2 7 -2" />
		{:else if terrain === 'iron_deposit'}
			<path d="M0 -4 L3.5 0 L0 4 L-3.5 0 Z M0 -4 L0 4 M-3.5 0 L3.5 0" />
		{:else if terrain === 'gold_vein'}
			<circle r="3.2" /><path d="M0 -1.8 L0 1.8" />
		{:else if terrain === 'plains'}
			<path d="M-3 2 l0.8 -2 M0 2.5 l0.8 -2 M3 2 l0.8 -2" />
		{/if}
	</g>
{/snippet}

<div class="hex-board" data-testid="board" data-layout="hex_map">
	<header class="round">
		<span class="label">Round</span>
		<strong data-testid="hex-round">{spec.round}</strong>
		<span class="of">of {spec.rounds_total}</span>
		<span class="track" aria-hidden="true"><i style="width: {progress * 100}%"></i></span>
		{#if !spoilers}
			<label class="eyes">
				<span>Map as seen by</span>
				<select
					value={through ?? spec.nations[0]?.id}
					onchange={(e) => seeAs(e.currentTarget.value)}
					data-testid="hex-nation"
				>
					{#each spec.nations as nation (nation.id)}
						<option value={nation.id}>{name(nation.id)}</option>
					{/each}
				</select>
			</label>
		{:else if hasFog}
			<label class="eyes">
				<span>Map as seen by</span>
				<select bind:value={eyes} data-testid="hex-eyes">
					<option value={null}>everyone (spectator)</option>
					{#each spec.nations as nation (nation.id)}
						<option value={nation.id}>{name(nation.id)}</option>
					{/each}
				</select>
			</label>
		{/if}
	</header>

	<svg
		class="map"
		viewBox={viewBox(spec.cols, spec.rows)}
		role="img"
		aria-label="Map, round {spec.round}: {spec.cities.length} cities, {spec.armies.length} armies"
		data-testid="hex-map"
	>
		<defs>
			<radialGradient id="hex-sheen" cx="50%" cy="35%" r="70%">
				<stop offset="0%" stop-color="#fff" stop-opacity="0.12" />
				<stop offset="100%" stop-color="#000" stop-opacity="0.18" />
			</radialGradient>
		</defs>

		{#each all as { tile, terrain } (String(tile))}
			{@const c = centre(tile)}
			<g class="tile" class:fogged={!visible(tile)} data-testid="hex-tile" data-terrain={terrain}>
				<polygon class="ground {terrain}" points={corners(tile, SIZE - 0.35)} />
				<polygon class="sheen" points={corners(tile, SIZE - 0.35)} fill="url(#hex-sheen)" />
				{@render glyph(terrain, c.x, c.y + SIZE * 0.35)}
				<title>{terrainName(terrain)} ({tile[0]}, {tile[1]})</title>
			</g>
		{/each}

		{#each fronts as front (`${front.a}-${front.b}`)}
			<line
				class="front"
				x1={front.from.x}
				y1={front.from.y}
				x2={front.to.x}
				y2={front.to.y}
				data-testid="hex-front"
			/>
		{/each}

		{#each spec.cities as city (city.id)}
			{@const c = centre(city.tile)}
			{#if visible(city.tile)}
				<g
					class="city"
					transform="translate({c.x} {c.y - SIZE * 0.15})"
					data-testid="hex-city"
					data-owner={city.owner}
				>
					{#if city.walls}
						<circle class="walls" r={SIZE * 0.62} stroke={colours[city.owner]} />
					{/if}
					<path
						class="crest"
						d="M-5 -4.5 H5 V1 Q5 5 0 6.5 Q-5 5 -5 1 Z"
						fill={colours[city.owner]}
						transform="scale({SIZE / 10})"
					/>
					<text class="pop" y={SIZE * 0.18}>{city.population}</text>
					{#if city.capital}
						<path
							class="star"
							d="M0 -3 L0.9 -0.9 L3 -0.9 L1.3 0.4 L1.9 2.6 L0 1.3 L-1.9 2.6 L-1.3 0.4 L-3 -0.9 L-0.9 -0.9 Z"
							transform="translate(0 {-SIZE * 0.72}) scale({SIZE / 14})"
						/>
					{/if}
					<title
						>{city.capital ? 'Capital' : 'City'} of {name(city.owner)}, population {city.population}{city.walls
							? ', walls'
							: ''}</title
					>
				</g>
			{/if}
		{/each}

		{#each armies as army (army.id)}
			{@const c = centre(army.tile)}
			{#if visible(army.tile)}
				<g
					class="army"
					transform="translate({c.x + army.dx} {c.y + SIZE * 0.45})"
					data-testid="hex-army"
					data-owner={army.owner}
				>
					<rect
						x={-SIZE * 0.42}
						y={-SIZE * 0.26}
						width={SIZE * 0.84}
						height={SIZE * 0.52}
						rx={SIZE * 0.12}
						fill={colours[army.owner]}
					/>
					<text class="strength" y={SIZE * 0.14}>{army.strength}</text>
					{#if army.fortified}
						<path
							class="fort"
							d="M-2 -2 H2 V0 Q2 2 0 2.6 Q-2 2 -2 0 Z"
							transform="translate({SIZE * 0.45} {-SIZE * 0.3}) scale({SIZE / 14})"
						/>
					{/if}
					<title
						>Army of {name(army.owner)}, strength {army.strength}{army.units
							? ': ' +
								Object.entries(army.units)
									.map(([u, n]) => `${n} ${u.replaceAll('_', ' ')}`)
									.join(', ')
							: ''}{army.fortified ? ', fortified' : ''}</title
					>
				</g>
			{/if}
		{/each}

		{#each spec.battles as battle, i (i)}
			{@const c = centre(battle.tile)}
			{#if visible(battle.tile)}
				<g class="battle" transform="translate({c.x} {c.y - SIZE * 0.55})" data-testid="hex-battle">
					<path
						d="M0 -4 L1.2 -1.3 L4 -1.8 L2 0.4 L3.4 3 L0.6 1.8 L-1 4 L-1.2 1.2 L-4 1.2 L-2 -0.8 L-3.2 -3.2 L-0.6 -1.6 Z"
						transform="scale({SIZE / 12})"
						stroke={battle.winner ? colours[battle.winner] : '#fff'}
					/>
					<title>Battle this round{battle.winner ? `, won by ${name(battle.winner)}` : ''}</title>
				</g>
			{/if}
		{/each}
	</svg>

	<ul class="nations" aria-label="Nations" data-testid="hex-nations">
		{#each spec.nations as nation (nation.id)}
			<li data-nation={nation.id} style="--nation: {colours[nation.id]}">
				<span class="swatch" aria-hidden="true"></span>
				<span class="who">
					<strong>{name(nation.id)}</strong>
					<small>{nation.cities} {nation.cities === 1 ? 'city' : 'cities'}</small>
				</span>
				<span class="rep" title="Reputation {nation.reputation} of 100">
					<span class="bar"><i style="width: {nation.reputation}%"></i></span>
					<small>{nation.reputation}</small>
				</span>
				{#if nation.stock}
					<span class="stock" data-testid="hex-stock">
						{#each Object.entries(nation.stock) as [resource, amount] (resource)}
							<span title={resource}><i class="res {resource}" aria-hidden="true"></i>{amount}</span
							>
						{/each}
					</span>
				{/if}
				{#if nation.at_war.length}
					<span class="war" data-testid="hex-war"
						>at war with {nation.at_war.map(name).join(', ')}</span
					>
				{/if}
			</li>
		{/each}
	</ul>

	{#if spec.treaties.length}
		<p class="treaties" data-testid="hex-treaties">
			{#each spec.treaties as treaty, i (i)}
				<span class="treaty"><b>{treaty.kind}</b> {treaty.parties.map(name).join(' & ')}</span>
			{/each}
		</p>
	{/if}

	<p class="legend" aria-label="Terrain">
		{#each legendTerrains as terrain (terrain)}
			<span
				><svg viewBox="-10 -10 20 20" aria-hidden="true"
					><polygon class="ground {terrain}" points={hexagon(0, 0, 9)} />{@render glyph(
						terrain,
						0,
						2
					)}</svg
				>{terrainName(terrain)}</span
			>
		{/each}
	</p>
</div>

<style>
	.hex-board {
		display: grid;
		gap: 0.6rem;
		padding: 0.75rem;
		border-radius: var(--radius);
		border: 1px solid var(--border);
		background: radial-gradient(circle at 50% 30%, #1b2333 0%, #10141d 85%);
	}

	.round {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem 0.6rem;
		font-size: 0.85rem;
	}

	.round .label {
		font-size: 0.72rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.round strong {
		font-size: 1.15rem;
		font-variant-numeric: tabular-nums;
	}

	.of {
		color: var(--muted);
	}

	.track {
		flex: 1 1 6rem;
		height: 0.35rem;
		border-radius: 999px;
		background: var(--surface-raised);
		overflow: hidden;
	}

	.track i {
		display: block;
		height: 100%;
		background: var(--accent);
	}

	.eyes {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.8rem;
		color: var(--muted);
	}

	.eyes select {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.2rem 0.6rem;
	}

	.map {
		width: 100%;
		height: auto;
		display: block;
	}

	.ground {
		stroke: #0b0e14;
		stroke-width: 0.5;
	}
	.ground.plains {
		fill: #7d9a4c;
	}
	.ground.forest {
		fill: #3d6a3c;
	}
	.ground.hills {
		fill: #93805a;
	}
	.ground.mountains {
		fill: #6c6874;
	}
	.ground.water {
		fill: #2b5d86;
	}
	.ground.river {
		fill: #6f9a5a;
	}
	.ground.iron_deposit {
		fill: #5f6677;
	}
	.ground.gold_vein {
		fill: #a8893c;
	}
	.ground.unknown {
		fill: #333;
	}

	.sheen {
		pointer-events: none;
	}

	.glyph {
		fill: none;
		stroke: #0007;
		stroke-width: 0.9;
		stroke-linecap: round;
		stroke-linejoin: round;
		pointer-events: none;
	}
	.glyph.forest path {
		fill: #244a2a;
		stroke: #1a3520;
	}
	.glyph.mountains path {
		fill: #4f4b57;
		stroke: #2f2c35;
	}
	.glyph.mountains .snow {
		fill: #e8e6ef;
		stroke: none;
	}
	.glyph.water path,
	.glyph.river path {
		stroke: #bfe3ff99;
	}
	.glyph.river path {
		stroke: #5fb7e6;
		stroke-width: 1.6;
	}
	.glyph.iron_deposit path {
		stroke: #d9dee8;
	}
	.glyph.gold_vein circle {
		fill: #f3cf62;
		stroke: #6d5212;
	}
	.glyph.gold_vein path {
		stroke: #6d5212;
	}

	.tile {
		transition: opacity 250ms ease;
	}

	.tile.fogged {
		opacity: 0.22;
		filter: grayscale(0.8);
	}

	.front {
		stroke: var(--danger);
		stroke-width: 0.8;
		stroke-dasharray: 2 1.5;
		opacity: 0.75;
	}

	.city .crest {
		stroke: #0b0e14;
		stroke-width: 0.8;
	}

	.walls {
		fill: none;
		stroke-width: 1.2;
		stroke-dasharray: 1.6 0.9;
	}

	.pop,
	.strength {
		text-anchor: middle;
		font-size: 4.6px;
		font-weight: 700;
		fill: #fff;
		paint-order: stroke;
		stroke: #0009;
		stroke-width: 0.8px;
	}

	.strength {
		font-size: 3.8px;
	}

	.star,
	.fort {
		fill: #ffd27f;
		stroke: #0b0e14;
		stroke-width: 0.4;
	}

	.army rect {
		stroke: #0b0e14;
		stroke-width: 0.7;
	}

	.battle path {
		fill: #ffeec8;
		stroke-width: 0.8;
		transform-box: fill-box;
		transform-origin: center;
		animation: flare 900ms ease-out both;
	}

	@keyframes flare {
		from {
			opacity: 0;
			scale: 0.4;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.battle path {
			animation: none;
		}
		.tile {
			transition: none;
		}
	}

	.nations {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(11.5rem, 1fr));
		gap: 0.4rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.nations li {
		display: grid;
		grid-template-columns: auto 1fr auto;
		align-items: center;
		gap: 0.15rem 0.5rem;
		padding: 0.4rem 0.6rem;
		border-radius: 10px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-left: 3px solid var(--nation);
		font-size: 0.8rem;
	}

	.swatch {
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 3px;
		background: var(--nation);
	}

	.who {
		display: grid;
		min-width: 0;
	}

	.who strong {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.who small,
	.rep small {
		color: var(--muted);
		font-size: 0.72rem;
	}

	.rep {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
	}

	.rep .bar {
		width: 3rem;
		height: 0.3rem;
		border-radius: 999px;
		background: var(--surface-raised);
		overflow: hidden;
	}

	.rep .bar i {
		display: block;
		height: 100%;
		background: var(--nation);
	}

	.stock {
		grid-column: 1 / -1;
		display: flex;
		gap: 0.6rem;
		font-variant-numeric: tabular-nums;
		color: var(--muted);
	}

	.stock span {
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
	}

	.res {
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 50%;
		background: var(--muted);
	}
	.res.food {
		background: #9ccf5a;
	}
	.res.wood {
		background: #8a5a35;
	}
	.res.iron {
		background: #b8c0cc;
	}
	.res.gold {
		background: #f3cf62;
	}

	.war {
		grid-column: 1 / -1;
		color: var(--danger);
		font-size: 0.75rem;
	}

	.treaties,
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem 0.8rem;
		margin: 0;
		font-size: 0.75rem;
		color: var(--muted);
	}

	.treaty {
		padding: 0.05rem 0.5rem;
		border-radius: 999px;
		border: 1px solid var(--border);
	}

	.treaty b {
		font-weight: 600;
		text-transform: capitalize;
		color: var(--text);
	}

	.legend span {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
	}

	.legend svg {
		width: 1.1rem;
		height: 1.1rem;
	}
</style>
