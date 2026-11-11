<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { MatchEvent, Seat, TranscriptLine } from '#lib/api.js';
	import Avatar from '#lib/components/Avatar.svelte';
	import Beats from '#lib/components/Beats.svelte';
	import Board from '#lib/components/Board.svelte';
	import Commentary from '#lib/components/Commentary.svelte';
	import { euros } from '#lib/live.js';
	import { seatModel, seatName, type Beat, type View } from '#lib/viewer.js';

	/**
	 * One match on screen, live or replayed: the cast, the board as the stage, the
	 * controls under it and the commentary beside it (under it on a phone).
	 */
	let {
		spec,
		view,
		events,
		lines,
		seats,
		players,
		costs,
		active = null,
		controls
	}: {
		spec: Record<string, unknown> | null;
		view: View;
		events: MatchEvent[];
		lines: TranscriptLine[];
		seats: string[];
		players: Record<string, Seat> | undefined;
		/** Micro-euros per seat, or null when nothing is known. */
		costs: Record<string, number> | null;
		active?: string | null;
		controls: Snippet;
	} = $props();

	let beat = $state<Beat | null>(null);
	/** Seat id to the key of its colour: the model, so a model looks the same in every match. */
	const colours = $derived(
		Object.fromEntries(seats.map((seat) => [seat, seatModel(seat, players) ?? seat]))
	);

	const names = $derived(Object.fromEntries(seats.map((seat) => [seat, seatName(seat, players)])));

	const out = $derived(
		new Set(
			((spec?.seats as { player?: string; alive?: boolean }[] | undefined) ?? [])
				.filter((seat) => seat.alive === false)
				.map((seat) => seat.player)
		)
	);
</script>

<div class="watch" data-view={view} data-testid="watch" data-events={events.length}>
	<ul class="cast" aria-label="Players" data-testid="cast">
		{#each seats as seat (seat)}
			{@const model = seatModel(seat, players)}
			<li class:active={active === seat} class:out={out.has(seat)} data-seat={seat}>
				<Avatar
					name={seatName(seat, players)}
					colourKey={model ?? seat}
					size={34}
					active={active === seat}
					out={out.has(seat)}
				/>
				<span class="who">
					<strong>{seatName(seat, players)}</strong>
					<small>{model ?? (players?.[seat] ? 'random bot' : seat)}</small>
				</span>
				{#if costs && model}
					<span class="cost" title="Model cost so far">{euros(costs[seat] ?? 0)}</span>
				{/if}
			</li>
		{/each}
	</ul>

	<div class="stage-column">
		<section class="stage" class:shake={beat === 'bang'} aria-label="Board" data-testid="stage">
			<div class="fit">
				<Board {spec} spoilers={view === 'spectator'} {events} {names} {colours} />
			</div>
			<Beats {lines} bind:current={beat} />
		</section>
		<div class="controls">{@render controls()}</div>
	</div>

	<Commentary {lines} {seats} {players} {view} />
</div>

<style>
	.watch {
		display: grid;
		gap: 0.9rem;
		padding-block: 0.75rem 2rem;
	}

	.cast {
		display: flex;
		gap: 0.5rem;
		margin: 0;
		padding: 0 0 0.25rem;
		list-style: none;
		overflow-x: auto;
		scrollbar-width: thin;
	}

	.cast li {
		flex: none;
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.3rem 0.75rem 0.3rem 0.3rem;
		border-radius: 999px;
		background: var(--surface);
		border: 1px solid var(--border);
		transition:
			border-color 200ms ease,
			opacity 200ms ease;
	}

	.cast li.active {
		border-color: var(--accent);
	}

	.cast li.out {
		opacity: 0.55;
	}

	.who {
		display: grid;
		line-height: 1.15;
	}

	.who strong {
		font-size: 0.875rem;
	}

	.who small {
		font-size: 0.75rem;
		color: var(--muted);
	}

	.cost {
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		color: var(--accent);
	}

	.stage-column {
		display: grid;
		gap: 0.75rem;
		min-width: 0;
		align-content: start;
	}

	.stage {
		position: relative;
		min-width: 0;
		padding: clamp(0.5rem, 2vw, 1.25rem);
		border-radius: calc(var(--radius) + 4px);
		background:
			radial-gradient(70% 60% at 50% 35%, rgb(240 179 90 / 0.1), transparent 70%), var(--surface);
		border: 1px solid var(--border);
		box-shadow: 0 20px 60px rgb(0 0 0 / 0.35);
	}

	/* A live chamber: the stage jolts once. Transform only, and not with reduced motion. */
	.stage.shake {
		animation: shake 420ms cubic-bezier(0.36, 0.07, 0.19, 0.97);
	}

	@keyframes shake {
		20%,
		60% {
			transform: translateX(-6px);
		}
		40%,
		80% {
			transform: translateX(6px);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.stage.shake {
			animation: none;
		}

		.cast li {
			transition: none;
		}
	}

	/* Square boards would grow past the screen; keep the stage and its controls in view. */
	.fit {
		max-width: min(100%, calc(100svh - 21rem));
		margin-inline: auto;
	}

	.controls {
		min-width: 0;
	}

	/* The commentary stays one screen tall and scrolls inside, so the page never grows. */
	.watch > :global(.commentary) {
		height: min(70vh, 40rem);
	}

	@media (min-width: 64rem) {
		.watch {
			grid-template-columns: minmax(0, 1.7fr) minmax(20rem, 1fr);
			grid-template-areas:
				'cast cast'
				'stage commentary';
			align-items: start;
		}

		.cast {
			grid-area: cast;
			flex-wrap: wrap;
		}

		.stage-column {
			grid-area: stage;
		}

		.watch > :global(.commentary) {
			grid-area: commentary;
			position: sticky;
			top: 1rem;
			height: calc(100vh - 2rem);
			max-height: 52rem;
		}
	}
</style>
