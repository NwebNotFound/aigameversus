<script lang="ts">
	import type { Seat } from '#lib/api.js';
	import Avatar from '#lib/components/Avatar.svelte';
	import { euros } from '#lib/live.js';
	import { ordinal, seatModel, seatName, type Result } from '#lib/viewer.js';

	/**
	 * How the match ended, on the stage: a podium for a ranked game, the winning side for a
	 * team game. The headline is the transcript's own line about the end.
	 */
	let {
		result,
		players,
		costs = null,
		onclose
	}: {
		result: Result;
		players: Record<string, Seat> | undefined;
		costs?: Record<string, number> | null;
		onclose: () => void;
	} = $props();

	const name = (seat: string) => seatName(seat, players);
	const model = (seat: string) => seatModel(seat, players);
	const colour = (seat: string) => model(seat) ?? seat;

	/** The podium shows the first three ranks, the winner in the middle. */
	const podium = $derived(
		result.kind === 'ranks' ? result.ranks.slice(0, 3).map((r, i) => ({ ...r, place: i })) : []
	);
	const rest = $derived(result.kind === 'ranks' ? result.ranks.slice(3) : []);
</script>

<div class="scrim" data-testid="result" data-kind={result.kind}>
	<section class="card" aria-labelledby="result-title">
		<header>
			<p class="eyebrow">Final result</p>
			<h2 id="result-title">{result.headline || 'Match over'}</h2>
		</header>

		{#if result.kind === 'team'}
			<div class="team winners" data-testid="winners">
				<p class="label">Won</p>
				<ul>
					{#each result.winners as seat (seat)}
						<li>
							<Avatar name={name(seat)} colourKey={colour(seat)} size={44} active />
							<strong>{name(seat)}</strong>
							{#if model(seat)}<small>{model(seat)}</small>{/if}
						</li>
					{/each}
				</ul>
			</div>
			{#if result.others.length}
				<div class="team others">
					<p class="label">Lost</p>
					<ul>
						{#each result.others as seat (seat)}
							<li>
								<Avatar name={name(seat)} colourKey={colour(seat)} size={30} out />
								<span>{name(seat)}</span>
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		{:else}
			<ol class="podium" data-testid="podium">
				{#each podium as step (step.rank)}
					<li class="step place-{step.place}" data-rank={step.rank}>
						<div class="who">
							{#each step.seats as seat (seat)}
								<span class="person">
									<Avatar
										name={name(seat)}
										colourKey={colour(seat)}
										size={step.place === 0 ? 52 : 40}
										active={step.place === 0}
									/>
									<strong>{name(seat)}</strong>
									{#if model(seat)}<small>{model(seat)}</small>{/if}
									{#if costs && model(seat) && (costs[seat] ?? 0) > 0}<small class="cost"
											>{euros(costs[seat] ?? 0)}</small
										>{/if}
								</span>
							{/each}
						</div>
						<div class="block"><span>{ordinal(step.rank)}</span></div>
					</li>
				{/each}
			</ol>
			{#if rest.length}
				<ol class="rest">
					{#each rest as row (row.rank)}
						{#each row.seats as seat (seat)}
							<li data-rank={row.rank}>
								<span class="rank">{ordinal(row.rank)}</span>
								<Avatar name={name(seat)} colourKey={colour(seat)} size={24} />
								<span>{name(seat)}</span>
								{#if model(seat)}<small>{model(seat)}</small>{/if}
							</li>
						{/each}
					{/each}
				</ol>
			{/if}
		{/if}

		<button class="close" onclick={onclose} data-testid="result-close">Show the board</button>
	</section>
</div>

<style>
	.scrim {
		position: absolute;
		inset: 0;
		z-index: 6;
		display: grid;
		place-items: center;
		padding: 0.75rem;
		border-radius: inherit;
		background: rgb(8 7 12 / 0.72);
		backdrop-filter: blur(3px);
		animation: fade 400ms ease-out;
	}

	.card {
		display: grid;
		gap: 1rem;
		width: min(34rem, 100%);
		max-height: 100%;
		overflow-y: auto;
		padding: 1.25rem 1.25rem 1rem;
		border-radius: calc(var(--radius) + 4px);
		background: linear-gradient(
			160deg,
			color-mix(in srgb, var(--accent) 12%, var(--surface)),
			var(--surface)
		);
		border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
		box-shadow: 0 24px 60px rgb(0 0 0 / 0.55);
		text-align: center;
	}

	.eyebrow,
	.label {
		margin: 0;
		font-size: 0.75rem;
		font-weight: 650;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--muted);
	}

	h2 {
		margin: 0.2rem 0 0;
		font-family: var(--font-narrator);
		font-size: clamp(1.15rem, 3.6vw, 1.6rem);
		line-height: 1.25;
		color: var(--accent);
	}

	ul,
	ol {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	/* Team result: the winning side large, the rest small and grey. */
	.team ul {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.75rem 1.1rem;
		margin-top: 0.5rem;
	}

	.team li {
		display: grid;
		justify-items: center;
		gap: 0.2rem;
		min-width: 4.5rem;
	}

	.team small,
	.person small {
		font-size: 0.75rem;
		color: var(--muted);
	}

	.others li {
		color: var(--muted);
		font-size: 0.875rem;
	}

	/* Podium: second, first, third. */
	.podium {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		align-items: end;
		gap: 0.5rem;
	}

	.step {
		display: grid;
		gap: 0.4rem;
	}

	.place-0 {
		order: 2;
	}
	.place-1 {
		order: 1;
	}
	.place-2 {
		order: 3;
	}

	.who {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.5rem;
	}

	.person {
		display: grid;
		justify-items: center;
		gap: 0.15rem;
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.person .cost {
		color: var(--accent);
		font-variant-numeric: tabular-nums;
	}

	.block {
		display: grid;
		place-items: center;
		border-radius: 8px 8px 2px 2px;
		background: var(--surface-raised);
		border: 1px solid var(--border);
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.place-0 .block {
		height: 4.25rem;
		color: var(--bg);
		background: linear-gradient(180deg, #ffd27f, var(--accent));
		border-color: var(--accent);
		font-size: 1.15rem;
	}
	.place-1 .block {
		height: 3rem;
	}
	.place-2 .block {
		height: 2.25rem;
	}

	.rest {
		display: grid;
		gap: 0.3rem;
		text-align: left;
	}

	.rest li {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding-top: 0.3rem;
		border-top: 1px solid var(--border);
		font-size: 0.875rem;
	}

	.rest .rank {
		width: 2.5rem;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}

	.rest small {
		margin-left: auto;
		color: var(--muted);
		font-size: 0.75rem;
	}

	.close {
		justify-self: center;
		font: inherit;
		font-size: 0.875rem;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.35rem 1rem;
		min-height: 2.25rem;
		cursor: pointer;
	}

	@keyframes fade {
		from {
			opacity: 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.scrim {
			animation: none;
		}
	}
</style>
