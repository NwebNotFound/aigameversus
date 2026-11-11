<script lang="ts">
	import { ordinal } from '#lib/event-text.js';
	import { euros } from '#lib/live.js';
	import { playerName, type Seats } from '#lib/players.js';

	/** How a match ended: the winners first, then everyone by rank, with model and cost. */
	let {
		placements,
		seats = null,
		costs = {}
	}: {
		placements: { player: string; rank: number }[];
		seats?: Seats;
		/** Millionths of a euro per seat. */
		costs?: Record<string, number>;
	} = $props();

	const ranked = $derived([...placements].sort((a, b) => a.rank - b.rank));
	const winners = $derived(ranked.filter((p) => p.rank === 1));
</script>

<section class="result" aria-labelledby="result-title" data-testid="result">
	<h2 id="result-title">Result</h2>
	<p class="winner">
		{#if winners.length === 1}
			<strong>{playerName(winners[0].player, seats)}</strong> wins
		{:else}
			<strong>{winners.map((w) => playerName(w.player, seats)).join(', ')}</strong> win together
		{/if}
	</p>
	<ol>
		{#each ranked as placement (placement.player)}
			{@const info = seats?.[placement.player]}
			<li class:first={placement.rank === 1} data-player={placement.player}>
				<span class="rank">{ordinal(placement.rank, 'en')}</span>
				<span class="name">{playerName(placement.player, seats)}</span>
				<span class="model">{info?.model_id ?? (info?.kind === 'bot' ? 'random bot' : '')}</span>
				{#if costs[placement.player]}
					<span class="cost">{euros(costs[placement.player])}</span>
				{/if}
			</li>
		{/each}
	</ol>
</section>

<style>
	.result {
		display: grid;
		gap: 0.5rem;
		margin-block: 1rem 0.5rem;
		padding: 1rem 1.25rem;
		border-radius: var(--radius);
		background: linear-gradient(
			135deg,
			color-mix(in srgb, var(--accent) 14%, var(--surface)),
			var(--surface)
		);
		border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
	}

	h2 {
		margin: 0;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--muted);
	}

	.winner {
		margin: 0;
		font-size: clamp(1.2rem, 4vw, 1.6rem);
	}

	ol {
		display: grid;
		gap: 0.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	li {
		display: grid;
		grid-template-columns: 3rem minmax(0, 1fr) auto auto;
		align-items: baseline;
		gap: 0.75rem;
		padding: 0.3rem 0;
		border-top: 1px solid var(--border);
	}

	li.first .name {
		font-weight: 700;
		color: var(--accent);
	}

	.rank,
	.model,
	.cost {
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}

	.name {
		overflow-wrap: anywhere;
	}

	@media (max-width: 30rem) {
		li {
			grid-template-columns: 2.5rem minmax(0, 1fr) auto;
		}

		.cost {
			display: none;
		}
	}
</style>
