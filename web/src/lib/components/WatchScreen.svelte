<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { MatchEvent, Seat, TranscriptLine } from '#lib/api.js';
	import Avatar from '#lib/components/Avatar.svelte';
	import Beats from '#lib/components/Beats.svelte';
	import Board from '#lib/components/Board.svelte';
	import Commentary from '#lib/components/Commentary.svelte';
	import ResultCard from '#lib/components/ResultCard.svelte';
	import { euros } from '#lib/live.js';
	import { waited } from '#lib/pacing.js';
	import {
		colourKey,
		resultOf,
		seatModel,
		seatName,
		seatSub,
		type Beat,
		type Placement,
		type View
	} from '#lib/viewer.js';

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
		placements = null,
		ended = false,
		thinking = null,
		responses = {},
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
		/** The final ranks, once the match is over. */
		placements?: Placement[] | null;
		/** The match is over and its end is on screen: show the result card. */
		ended?: boolean;
		/** The seat a model is answering for right now, and for how long (live only). */
		thinking?: { seat: string; ms: number } | null;
		/** Each seat's last response time in ms, from the decision events. */
		responses?: Record<string, number>;
		controls: Snippet;
	} = $props();

	let beat = $state<Beat | null>(null);

	/** The chip's tooltip: model, vendor, price per million tokens and the cost so far. */
	function chipTitle(seat: string): string {
		const info = players?.[seat];
		const parts = [seatName(seat, players)];
		if (info?.model) parts.push(info.vendor ? `${info.model} by ${info.vendor}` : info.model);
		if (info?.personality) parts.push(`personality: ${info.personality}`);
		if (info?.price) {
			parts.push(`$${info.price.input} in / $${info.price.output} out per 1M tokens`);
		}
		if (costs && (info?.kind === 'model' || info?.model))
			parts.push(`spent so far: ${euros(costs[seat] ?? 0)}`);
		if (info?.kind === 'bot') parts.push('plays random legal moves, no model');
		return parts.join('\n');
	}
	const result = $derived(ended ? resultOf(placements, lines) : null);
	/** The viewer closed the card to look at the board; it comes back at the next end. */
	let dismissed = $state(false);
	$effect(() => {
		if (!ended) dismissed = false;
	});
	/** Seat id to the key of its colour: the model, so a model looks the same in every match. */
	const colours = $derived(
		Object.fromEntries(seats.map((seat) => [seat, colourKey(seat, players)]))
	);

	/** The small line under a seat's name on the board: model id (if not the name) and vendor. */
	const subs = $derived(Object.fromEntries(seats.map((seat) => [seat, seatSub(seat, players)])));

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
			{@const info = players?.[seat]}
			{@const model = seatModel(seat, players)}
			{@const isModel = info?.kind === 'model' || !!model}
			<li
				class:asked={thinking?.seat === seat}
				class:active={active === seat}
				class:out={out.has(seat)}
				data-seat={seat}
				data-kind={isModel ? 'model' : (info?.kind ?? 'seat')}
				title={chipTitle(seat)}
			>
				<Avatar
					name={seatName(seat, players)}
					colourKey={colours[seat]}
					size={34}
					active={active === seat}
					out={out.has(seat)}
				/>
				<span class="who">
					<span class="line1">
						<strong>{seatName(seat, players)}</strong>
						{#if isModel}<span class="kind model">model</span>{/if}
					</span>
					{#if subs[seat]}<small data-testid="chip-model">{subs[seat]}</small>{/if}
					{#if info?.personality}<small class="persona">{info.personality}</small>{/if}
				</span>
				{#if thinking?.seat === seat}
					<span class="thinking" data-testid="thinking" title="Waiting for this player's answer"
						>thinking… {waited(thinking.ms)}</span
					>
				{:else if responses[seat] !== undefined}
					<span class="response" title="Response time of the last move"
						>{(responses[seat] / 1000).toFixed(1)} s</span
					>
				{/if}
				{#if costs && isModel}
					<span class="cost">{euros(costs[seat] ?? 0)}</span>
				{/if}
			</li>
		{/each}
	</ul>

	<div class="stage-column">
		<section class="stage" class:shake={beat === 'bang'} aria-label="Board" data-testid="stage">
			<div class="fit">
				<Board {spec} spoilers={view === 'spectator'} {events} {names} {colours} {subs} />
			</div>
			<Beats {lines} bind:current={beat} />
			{#if result && !dismissed}
				<ResultCard {result} {players} {costs} onclose={() => (dismissed = true)} />
			{/if}
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

	.line1 {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}

	.kind {
		font-size: 0.75rem;
		line-height: 1.2;
		padding: 0 0.35rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
	}

	.kind.model {
		color: var(--accent-2);
		border-color: color-mix(in srgb, var(--accent-2) 45%, transparent);
	}

	.persona {
		font-style: italic;
	}

	.thinking {
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		color: var(--accent-2);
	}

	.response {
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		color: var(--muted);
	}

	/* A model is answering: its chip breathes, gently. */
	.cast li.asked {
		border-color: var(--accent-2);
		animation: asked 1.8s ease-in-out infinite;
	}

	@keyframes asked {
		50% {
			box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent-2) 30%, transparent);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.cast li.asked {
			animation: none;
		}
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
