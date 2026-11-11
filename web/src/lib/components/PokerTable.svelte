<script lang="ts">
	import type { MatchEvent } from '#lib/api.js';
	import {
		actionChips,
		card,
		coins,
		percent,
		positionTag,
		seatPoint
	} from '#lib/boards/pokerTable.js';
	import Avatar from '#lib/components/Avatar.svelte';
	import { hidden } from '#lib/live.js';
	import { seatHue } from '#lib/viewer.js';

	/**
	 * The Poker table: an oval with a seat per player (avatar, chip stack, hole cards,
	 * position), the five community cards, the pot and any side pots. With spoilers on, hole
	 * cards are face up and each player shows a chance to win; with spoilers off, only backs.
	 */
	let {
		spec,
		spoilers,
		events = [],
		names = {},
		colours = {}
	}: {
		spec: Record<string, unknown>;
		spoilers: boolean;
		events?: MatchEvent[];
		names?: Record<string, string>;
		colours?: Record<string, string>;
	} = $props();
	const label = (seat: string) => names[seat] ?? seat;

	interface Seat {
		player: string;
		stack: number;
		cards: string[];
		folded: boolean;
		position: string | null;
		win_probability: number | null;
	}
	interface Pot {
		amount: number;
		eligible: string[];
	}

	const seats = $derived(spec.seats as Seat[]);
	const board = $derived((spec.board as string[]) ?? []);
	const pots = $derived(((spec.side_pots as Pot[]) ?? []).filter((pot) => pot.amount > 0));
	const hideCards = $derived(hidden('cards', spoilers));
	const slots = $derived(Array.from({ length: 5 }, (_, i) => board[i] ?? null));

	const chips = $derived(actionChips(events));
	/** Chips in the middle: a hand is being played. Between hands and after the last one, no pot or odds. */
	const inPlay = $derived(Number(spec.pot) > 0);
	/** No chips left and no hand running for them: out of the tournament. */
	const busted = (seat: Seat) => seat.stack === 0 && (seat.cards.length === 0 || !inPlay);
	/** The seat's colour, from its model: the same model has the same chips everywhere. */
	const colour = (seat: string) => `oklch(0.75 0.12 ${seatHue(colours[seat] ?? seat)})`;
</script>

<div class="table" data-testid="board" data-layout="poker_table">
	<div class="felt" aria-hidden="true"></div>

	<div class="middle">
		<div class="street" data-testid="street">
			{#if spec.street}{spec.street} ·
			{/if}hand {spec.hand}
		</div>
		<div class="community" data-testid="community" aria-label="Community cards">
			{#each slots as slot, i (i)}
				{@const c = slot ? card(slot) : null}
				{#if c}
					<span class="card face" class:red={c.red} aria-label={c.label}>
						<b>{c.rank}</b><i>{c.symbol}</i>
					</span>
				{:else}
					<span class="card slot" aria-hidden="true"></span>
				{/if}
			{/each}
		</div>
		{#if inPlay}<div class="pot" data-testid="pot">Pot {spec.pot}</div>{/if}
		{#if pots.length > 1}
			<ul class="pots" data-testid="side-pots">
				{#each pots as pot, i (i)}
					<li>{i === 0 ? 'Main' : `Side ${i}`}: {pot.amount} ({pot.eligible.join(', ')})</li>
				{/each}
			</ul>
		{/if}
	</div>

	{#each seats as seat, index (seat.player)}
		{@const point = seatPoint(index, seats.length)}
		{@const tag = positionTag(seat.position)}
		<section
			class="seat"
			class:folded={seat.folded}
			class:broke={busted(seat)}
			style="left: {point.left}%; top: {point.top}%"
			data-testid="seat"
			aria-label={label(seat.player)}
		>
			<header>
				<Avatar
					name={label(seat.player)}
					colourKey={colours[seat.player] ?? seat.player}
					size={26}
					active={seat.player === spec.turn}
					out={busted(seat)}
				/>
				<strong>{label(seat.player)}</strong>
				{#if tag}<span class="tag" class:dealer={tag === 'D'} data-testid="position">{tag}</span
					>{/if}
				{#if seat.folded}<span class="tag">folded</span>{/if}
			</header>

			<div class="cards">
				{#if seat.cards.length === 0}
					<span class="muted">–</span>
				{:else if hideCards}
					<span class="backs" data-testid="secret" aria-label="{seat.cards.length} cards, hidden">
						{#each seat.cards as c (c)}<i class="card back"></i>{/each}
					</span>
				{:else}
					<span class="backs">
						{#each seat.cards as text (text)}
							{@const c = card(text)}
							{#if c}
								<span class="card face" class:red={c.red} aria-label={c.label}>
									<b>{c.rank}</b><i>{c.symbol}</i>
								</span>
							{/if}
						{/each}
					</span>
				{/if}
			</div>

			{#if busted(seat)}
				<span class="tag out" data-testid="out">out</span>
			{:else}
				<div class="chips" data-testid="stack">
					<svg viewBox="0 0 24 24" aria-hidden="true">
						{#each Array.from({ length: coins(seat.stack) }, (_, k) => k) as k (k)}
							<ellipse
								cx="12"
								cy={19 - k * 3}
								rx="9"
								ry="3"
								fill={colour(seat.player)}
								stroke="#0006"
								stroke-width="0.7"
							/>
						{/each}
					</svg>
					<span class="amount">{seat.stack}</span>
				</div>
			{/if}

			{#if chips[seat.player]}
				{#key chips[seat.player].label}
					<div class="action {chips[seat.player].kind}" data-testid="action-chip">
						{chips[seat.player].label}
					</div>
				{/key}
			{/if}

			{#if inPlay && !hideCards && seat.win_probability !== null && !seat.folded}
				<div class="chance" data-testid="win-chance">{percent(seat.win_probability)} to win</div>
			{/if}
		</section>
	{/each}
</div>

<style>
	.table {
		position: relative;
		width: 100%;
		aspect-ratio: 1 / 1;
		min-height: 28rem;
	}

	.felt {
		position: absolute;
		inset: 8% 4%;
		border-radius: 50%;
		background: radial-gradient(ellipse at center, #1f4a38 0%, #12281f 72%);
		border: 5px solid #3a2f24;
		box-shadow: inset 0 0 40px #000a;
	}

	.middle {
		position: absolute;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		display: grid;
		justify-items: center;
		gap: 0.3rem;
		z-index: 1;
		width: 55%;
		text-align: center;
	}

	.street {
		color: var(--muted);
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}

	.community {
		display: flex;
		gap: 0.2rem;
		justify-content: center;
	}

	.pot {
		font-weight: 700;
		color: var(--accent);
	}

	.pots {
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 0.7rem;
		color: var(--muted);
	}

	.card {
		display: inline-grid;
		place-items: center;
		width: 1.6rem;
		height: 2.3rem;
		border-radius: 4px;
		font-size: 0.8rem;
		line-height: 1;
	}

	.card.face {
		background: #f3ead8;
		color: #2a2118;
		border: 1px solid #b9ab8f;
		align-content: center;
	}

	.card.face.red {
		color: #b3202f;
	}

	.card.face i {
		font-style: normal;
		font-size: 0.75rem;
	}

	.card.back {
		background: repeating-linear-gradient(45deg, #1f3550 0 3px, #14243a 3px 6px);
		border: 1px solid #3a5a85;
	}

	.card.slot {
		border: 1px dashed #ffffff40;
	}

	.seat {
		position: absolute;
		transform: translate(-50%, -50%);
		z-index: 2;
		display: grid;
		justify-items: center;
		gap: 0.2rem;
		padding: 0.3rem 0.5rem;
		min-width: 5.5rem;
		border-radius: var(--radius);
		background: color-mix(in srgb, var(--surface) 90%, transparent);
		border: 1px solid var(--border);
		text-align: center;
	}

	.seat.folded {
		opacity: 0.45;
		filter: grayscale(1);
	}

	.seat.broke {
		border-style: dashed;
	}

	header {
		display: flex;
		align-items: center;
		justify-content: center;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.tag {
		font-size: 0.75rem;
		padding: 0.02rem 0.35rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
	}

	.tag.dealer {
		background: var(--accent);
		border-color: var(--accent);
		color: #1a1408;
		font-weight: 700;
	}

	.backs {
		display: flex;
		gap: 0.15rem;
		justify-content: center;
	}

	.muted {
		color: var(--muted);
	}

	.chips {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.chips svg {
		width: 1.4rem;
		height: 1.4rem;
	}

	.amount {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
		font-size: 0.85rem;
	}

	.chance {
		font-size: 0.7rem;
		color: var(--accent-2);
	}

	@media (max-width: 30rem) {
		.table {
			aspect-ratio: 3 / 4;
			min-height: 32rem;
		}
		.felt {
			inset: 14% 2%;
		}
		.middle {
			width: 80%;
		}
		.seat {
			min-width: 4.4rem;
			padding: 0.25rem 0.3rem;
			font-size: 0.8rem;
		}
		.card {
			width: 1.25rem;
			height: 1.8rem;
			font-size: 0.7rem;
		}
	}
	/* The last action of the street, next to the seat; all-in in brass. */
	.action {
		justify-self: center;
		padding: 0.05rem 0.5rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 650;
		font-variant-numeric: tabular-nums;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		animation: chip-in 300ms ease-out;
	}

	.action.all_in {
		color: var(--bg);
		background: var(--accent);
		border-color: var(--accent);
	}

	.action.fold {
		color: var(--muted);
	}

	@keyframes chip-in {
		from {
			transform: translateY(4px);
			opacity: 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.action {
			animation: none;
		}
	}
</style>
