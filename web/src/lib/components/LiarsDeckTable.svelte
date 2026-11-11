<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { MatchEvent } from '#lib/api.js';
	import { face, moments, sides, tableCardName, type Moment } from '#lib/boards/liarsDeck.js';
	import { hidden } from '#lib/live.js';

	/**
	 * The bar table of Liar's Deck: a round table with 2 to 4 seats, a card stand and a
	 * revolver per seat, the table card and the last play in the middle. `events` is the
	 * match log so far; new calls and shots get a short banner with a pause.
	 */
	let {
		spec,
		spoilers,
		events = [],
		names = {},
		active = []
	}: {
		spec: Record<string, unknown>;
		spoilers: boolean;
		events?: MatchEvent[];
		names?: Record<string, string>;
		active?: string[];
	} = $props();

	interface Seat {
		player: string;
		alive: boolean;
		hand: string[];
		trigger_pulls: number;
		chambers: number;
	}
	interface Play {
		player: string;
		cards: string[];
	}

	const seats = $derived(spec.seats as Seat[]);
	const lastPlay = $derived((spec.last_play ?? null) as Play | null);
	const places = $derived(sides(seats.length));
	const hideHands = $derived(hidden('hand', spoilers));
	const hidePlay = $derived(hidden('cards', spoilers));

	const HOLD_MS = 1300;
	let banner = $state<Moment | null>(null);
	let queue: Moment[] = [];
	let timer: ReturnType<typeof setTimeout> | undefined;
	/** The log up to this position was there when the table appeared, or has been shown. */
	let shown = -1;
	let started = false;

	function next() {
		const moment = queue.shift();
		banner = moment ?? null;
		if (moment) timer = setTimeout(next, HOLD_MS);
	}

	$effect(() => {
		const newest = events.length ? events[events.length - 1].seq : -1;
		if (!started) {
			// The backlog of a match that is already running (or over) is not replayed as drama.
			started = true;
			shown = newest;
			return;
		}
		const fresh = moments(events, shown);
		shown = Math.max(shown, newest);
		if (fresh.length === 0) return;
		queue.push(...fresh.slice(-6));
		if (!banner) next();
	});

	onDestroy(() => clearTimeout(timer));

	const palette = ['#f0b35a', '#7fb8ff', '#7ad69a', '#ff7a7a'];
	const colour = (index: number) => palette[index % palette.length];
</script>

<div class="table" data-testid="board" data-layout="card_table">
	<p class="sr-only" aria-live="polite" data-testid="banner-text">{banner?.text ?? ''}</p>

	<div class="felt" aria-hidden="true"></div>

	<div class="middle">
		<div class="round">Round {spec.round}</div>
		<div class="table-card" data-testid="table-card" aria-label="Table card">
			<span class="mark">{tableCardName(spec.table_card)}</span>
		</div>
		<div class="play" data-testid="last-play">
			{#if lastPlay}
				<span class="who">{lastPlay.player} played {lastPlay.cards.length}</span>
				{#if hidePlay}
					<span
						class="backs"
						data-testid="secret"
						aria-label="{lastPlay.cards.length} cards, face down"
					>
						{#each lastPlay.cards as card (card)}<i class="card back"></i>{/each}
					</span>
				{:else}
					<span class="backs">
						{#each lastPlay.cards as card (card)}
							{@const f = face(card)}
							<span class="card face" class:joker={f.joker} aria-label={f.label}>
								<b>{f.mark}</b><small>{f.index}</small>
							</span>
						{/each}
					</span>
				{/if}
			{:else}
				<span class="who">No play yet</span>
			{/if}
		</div>
	</div>

	{#each seats as seat, index (seat.player)}
		<section
			class="seat {places[index]}"
			class:out={!seat.alive}
			class:turn={seat.player === spec.turn}
			class:active={active.includes(seat.player)}
			data-testid="seat"
			data-seat={seat.player}
			aria-label={names[seat.player] ?? seat.player}
		>
			<header>
				<svg class="avatar" viewBox="0 0 40 40" aria-hidden="true">
					<circle
						cx="20"
						cy="20"
						r="19"
						fill="var(--surface-raised)"
						stroke={colour(index)}
						stroke-width="2"
					/>
					<text x="20" y="26" text-anchor="middle" font-size="18" fill={colour(index)}>
						{seat.player.slice(-1).toUpperCase()}
					</text>
				</svg>
				<strong>{names[seat.player] ?? seat.player}</strong>
				{#if seat.player === spec.turn}<span class="tag act">to act</span>{/if}
				{#if !seat.alive}<span class="tag">out</span>{/if}
			</header>

			<div class="stand" data-testid="stand">
				<span class="count" data-testid="card-count">{seat.hand.length} cards</span>
				{#if hideHands}
					<span class="hand" data-testid="secret" aria-label="{seat.hand.length} cards, hidden">
						{#each seat.hand as card (card)}<i class="card back"></i>{/each}
					</span>
				{:else}
					<span class="hand">
						{#each seat.hand as card (card)}
							{@const f = face(card)}
							<span
								class="card face"
								class:joker={f.joker}
								class:devil={f.devil}
								aria-label={f.label}
							>
								<b>{f.mark}</b><small>{f.index}</small>
							</span>
						{/each}
					</span>
				{/if}
			</div>

			<div
				class="revolver"
				data-testid="revolver"
				aria-label="Revolver {seat.trigger_pulls} of {seat.chambers}"
			>
				<svg viewBox="0 0 44 44" aria-hidden="true">
					<circle cx="22" cy="22" r="20" fill="var(--surface)" stroke="var(--border)" />
					{#each Array.from({ length: seat.chambers }, (_, i) => i) as chamber (chamber)}
						{@const angle = (chamber / seat.chambers) * 2 * Math.PI - Math.PI / 2}
						<circle
							cx={22 + 12 * Math.cos(angle)}
							cy={22 + 12 * Math.sin(angle)}
							r="4"
							fill={chamber < seat.trigger_pulls ? 'var(--danger)' : 'var(--surface-raised)'}
							stroke="var(--muted)"
							stroke-width="0.8"
						/>
					{/each}
				</svg>
				<span class="ratio">{seat.trigger_pulls}/{seat.chambers}</span>
			</div>
		</section>
	{/each}

	{#if banner}
		<div
			class="banner {banner.kind}"
			class:bang={banner.kind === 'shot' && banner.live}
			role="status"
			data-testid="banner"
		>
			{banner.text}
		</div>
	{/if}
</div>

<style>
	.table {
		position: relative;
		display: grid;
		grid-template-areas:
			'. top .'
			'left mid right'
			'. bottom .';
		grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr) minmax(0, 1fr);
		gap: 0.5rem;
		padding: 0.5rem;
		min-height: 22rem;
	}

	.felt {
		position: absolute;
		inset: 12% 8%;
		border-radius: 50%;
		background: radial-gradient(ellipse at center, #1f3b33 0%, #14241f 70%);
		border: 4px solid #3a2f24;
		box-shadow: inset 0 0 30px #0008;
		z-index: 0;
	}

	.middle {
		grid-area: mid;
		position: relative;
		z-index: 1;
		display: grid;
		justify-items: center;
		align-content: center;
		gap: 0.4rem;
		text-align: center;
	}

	.round {
		color: var(--muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.table-card {
		display: grid;
		place-items: center;
		width: 4.2rem;
		height: 5.6rem;
		border-radius: 8px;
		background: #f3ead8;
		color: #2a2118;
		border: 2px solid var(--accent);
		font-weight: 700;
		font-size: 0.95rem;
	}

	.play {
		display: grid;
		justify-items: center;
		gap: 0.2rem;
		font-size: 0.8rem;
	}

	.backs,
	.hand {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.15rem;
	}

	.card {
		display: inline-grid;
		place-items: center;
		width: 1.5rem;
		height: 2.1rem;
		border-radius: 4px;
		font-size: 0.75rem;
		line-height: 1;
	}

	.card.back {
		background: repeating-linear-gradient(45deg, #5a2230 0 3px, #3d1621 3px 6px);
		border: 1px solid #8a3a4c;
	}

	.card.face {
		background: #f3ead8;
		color: #2a2118;
		border: 1px solid #b9ab8f;
		grid-template-rows: auto auto;
		align-content: center;
	}

	.card.face.joker {
		color: #8a1f2d;
	}

	.card.face.devil {
		background: #2a0f16;
		color: #ff7a7a;
		border-color: #ff7a7a;
	}

	.card small {
		font-size: 0.55rem;
		opacity: 0.7;
	}

	.seat {
		position: relative;
		z-index: 1;
		display: grid;
		gap: 0.3rem;
		justify-items: center;
		padding: 0.4rem 0.5rem;
		border-radius: var(--radius);
		background: color-mix(in srgb, var(--surface) 88%, transparent);
		border: 1px solid var(--border);
		min-width: 0;
		text-align: center;
	}

	.seat.bottom {
		grid-area: bottom;
	}
	.seat.top {
		grid-area: top;
	}
	.seat.left {
		grid-area: left;
	}
	.seat.right {
		grid-area: right;
	}

	.seat.turn {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 40%, transparent);
	}

	.seat.out {
		opacity: 0.45;
		filter: grayscale(1);
	}

	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: center;
		gap: 0.3rem;
	}

	.avatar {
		width: 1.7rem;
		height: 1.7rem;
	}

	.tag {
		font-size: 0.65rem;
		padding: 0.05rem 0.4rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
	}

	.tag.act {
		color: var(--accent);
		border-color: var(--accent);
	}

	.count {
		font-size: 0.75rem;
		color: var(--muted);
	}

	.stand {
		display: grid;
		justify-items: center;
		gap: 0.2rem;
	}

	.revolver {
		display: flex;
		align-items: center;
		gap: 0.3rem;
	}

	.revolver svg {
		width: 1.9rem;
		height: 1.9rem;
	}

	.ratio {
		font-variant-numeric: tabular-nums;
		font-size: 0.8rem;
	}

	.banner {
		position: absolute;
		inset: 0;
		z-index: 3;
		display: grid;
		place-items: center;
		background: #000a;
		font-size: clamp(1.25rem, 5vw, 2rem);
		font-weight: 800;
		text-align: center;
		padding: 1rem;
		border-radius: var(--radius);
		animation: pop 0.25s ease-out;
	}

	.banner.liar {
		color: var(--accent);
	}

	.banner.shot {
		color: var(--text);
	}

	.banner.bang {
		color: var(--danger);
		background: #3a0a10cc;
	}

	@keyframes pop {
		from {
			transform: scale(0.9);
			opacity: 0;
		}
		to {
			transform: scale(1);
			opacity: 1;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.banner {
			animation: none;
		}
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}

	@media (max-width: 30rem) {
		.table {
			grid-template-areas:
				'top top top'
				'left mid right'
				'bottom bottom bottom';
			min-height: 0;
		}
		.felt {
			inset: 22% 2%;
		}
		.card {
			width: 1.2rem;
			height: 1.7rem;
		}
	}

	/* The player of the event just shown. */
	.active {
		box-shadow:
			0 0 0 2px var(--accent),
			0 0 16px color-mix(in srgb, var(--accent) 60%, transparent);
		transition: box-shadow 0.3s;
	}
</style>
