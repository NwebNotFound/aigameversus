<script lang="ts">
	import { tick } from 'svelte';
	import type { Seat, TranscriptLine } from '#lib/api.js';
	import { card } from '#lib/boards/pokerTable.js';
	import Avatar from '#lib/components/Avatar.svelte';
	import {
		commentary,
		ordinal,
		seatModel,
		seatName,
		showdownHands,
		words,
		type Placement,
		type View
	} from '#lib/viewer.js';

	/**
	 * The commentary column of the watch screen: the transcript, newest at the bottom.
	 * Every text comes from the transcript line; player words are shown as text, never HTML.
	 */
	let {
		lines,
		seats,
		players,
		view
	}: {
		lines: TranscriptLine[];
		seats: string[];
		players: Record<string, Seat> | undefined;
		view: View;
	} = $props();

	let tab = $state<'all' | 'thoughts'>('all');
	let who = $state('all');
	let bookkeeping = $state(false);
	let list = $state<HTMLOListElement>();
	let pinned = true;

	const shown = $derived(
		commentary(lines, bookkeeping)
			.filter((line) => tab === 'all' || line.kind === 'thought' || line.kind === 'whisper')
			.filter((line) => who === 'all' || line.actor === who)
	);

	// Follow the newest line unless the reader scrolled up to read.
	$effect(() => {
		void shown.length;
		if (!pinned || !list) return;
		tick().then(() => list?.scrollTo({ top: list.scrollHeight }));
	});

	function onscroll() {
		if (!list) return;
		pinned = list.scrollHeight - list.scrollTop - list.clientHeight < 48;
	}

	const name = (seat: string | null) => (seat ? seatName(seat, players) : '');
	/** The final ranks of a `match_finished` line, best first. */
	const ranksOf = (line: TranscriptLine) =>
		[...(((line.raw?.data as { placements?: Placement[] })?.placements ?? []) as Placement[])].sort(
			(a, b) => a.rank - b.rank
		);
	const colour = (seat: string) => seatModel(seat, players) ?? seat;
</script>

<section class="commentary" aria-labelledby="commentary-title">
	<header>
		<h2 id="commentary-title">Commentary</h2>
		<div class="tools">
			{#if view === 'spectator'}
				<div class="tabs" role="tablist" aria-label="Lines">
					<button role="tab" aria-selected={tab === 'all'} onclick={() => (tab = 'all')}>All</button
					>
					<button
						role="tab"
						aria-selected={tab === 'thoughts'}
						onclick={() => (tab = 'thoughts')}
						data-testid="tab-thoughts">Thoughts</button
					>
				</div>
			{/if}
			<label class="sr-only" for="who">Player</label>
			<select id="who" bind:value={who} data-testid="commentary-player">
				<option value="all">Everyone</option>
				{#each seats as seat (seat)}
					<option value={seat}>{name(seat)}</option>
				{/each}
			</select>
		</div>
	</header>

	<ol class="feed" bind:this={list} {onscroll} data-testid="commentary" aria-live="polite">
		{#if shown.length === 0}
			<li class="empty">Nothing yet.</li>
		{/if}
		{#each shown as line, index (line.seq ?? `x${index}`)}
			<li
				class="line {line.kind}"
				class:highlight={line.importance === 3}
				data-seq={line.seq}
				data-kind={line.kind}
				data-actor={line.actor}
				data-importance={line.importance}
			>
				{#if line.kind === 'heading'}
					<span class="heading-text">{line.text}</span>
					{#if line.detail}<small>{line.detail}</small>{/if}
				{:else if (line.kind === 'speech' || line.kind === 'whisper' || line.kind === 'thought') && line.actor}
					<Avatar name={name(line.actor)} colourKey={colour(line.actor)} size={30} />
					<div class="said">
						<span class="who">
							{name(line.actor)}
							{#if line.kind === 'thought'}
								<span class="tag thought-tag">
									<svg viewBox="0 0 12 12" aria-hidden="true"
										><rect x="2" y="5" width="8" height="6" rx="1.5" /><path
											d="M4 5V3.6a2 2 0 0 1 4 0V5"
										/></svg
									>
									thinks · players can't see this
								</span>
							{:else if line.kind === 'whisper'}
								<span class="tag whisper-tag">whispers</span>
							{/if}
						</span>
						<p class="bubble">{words(line) ?? line.text}</p>
					</div>
				{:else if line.raw?.type === 'match_finished' && ranksOf(line).length}
					<div class="final" data-testid="final-ranks">
						<span class="label">Final ranking</span>
						<ol>
							{#each ranksOf(line) as place (place.player)}
								<li class:first={place.rank === 1}>
									<span class="rank">{ordinal(place.rank)}</span>
									<Avatar name={name(place.player)} colourKey={colour(place.player)} size={22} />
									<span>{name(place.player)}</span>
								</li>
							{/each}
						</ol>
					</div>
				{:else if line.raw?.type === 'showdown' && showdownHands(lines, lines.indexOf(line)).length}
					<div class="showdown" data-testid="showdown">
						<span class="label">Showdown</span>
						{#each showdownHands(lines, lines.indexOf(line)) as hand (hand.player)}
							<div class="hand-row" class:won={hand.won > 0}>
								<Avatar name={name(hand.player)} colourKey={colour(hand.player)} size={24} />
								<span class="hand-who">{name(hand.player)}</span>
								<span class="hand-cards">
									{#each hand.cards as text (text)}
										{@const c = card(text)}
										{#if c}<span class="mini" class:red={c.red} aria-label={c.label}
												>{c.rank}{c.symbol}</span
											>{/if}
									{/each}
								</span>
								<span class="hand-kind">{hand.hand}</span>
								{#if hand.won > 0}<span class="hand-won">+{hand.won}</span>{/if}
							</div>
						{/each}
					</div>
				{:else if line.kind === 'narration'}
					<p class="narration">{line.text}</p>
				{:else if line.kind === 'info'}
					<small class="info">{line.text}</small>
				{:else}
					{#if line.actor}
						<Avatar name={name(line.actor)} colourKey={colour(line.actor)} size={24} />
					{/if}
					<div class="told">
						<span>{line.text}</span>
						{#if line.detail}<small>{line.detail}</small>{/if}
					</div>
				{/if}
			</li>
		{/each}
	</ol>

	<label class="bookkeeping">
		<input type="checkbox" bind:checked={bookkeeping} />
		Show bookkeeping
	</label>
</section>

<style>
	.commentary {
		display: flex;
		flex-direction: column;
		min-width: 0;
		min-height: 0;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
		overflow: hidden;
	}

	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.75rem 0.9rem;
		border-bottom: 1px solid var(--border);
	}

	h2 {
		margin: 0;
		font-size: 0.8rem;
		font-weight: 650;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--muted);
	}

	.tools,
	.tabs {
		display: flex;
		align-items: center;
		gap: 0.35rem;
	}

	.tabs button,
	select {
		font: inherit;
		font-size: 0.875rem;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0.25rem 0.75rem;
		min-height: 2rem;
		cursor: pointer;
	}

	select {
		max-width: 11rem;
	}

	.tabs button[aria-selected='true'] {
		color: var(--bg);
		background: var(--accent);
		border-color: var(--accent);
	}

	.feed {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
		margin: 0;
		padding: 0.75rem 0.9rem 1rem;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
		scroll-behavior: smooth;
	}

	.line {
		display: flex;
		align-items: flex-start;
		gap: 0.55rem;
		overflow-wrap: anywhere;
	}

	.empty {
		color: var(--muted);
	}

	/* Narrator: chapter divider. */
	.heading {
		flex-direction: column;
		align-items: center;
		gap: 0.1rem;
		margin-top: 0.6rem;
		padding-top: 0.6rem;
		border-top: 1px solid var(--border);
		text-align: center;
	}

	.heading-text {
		font-family: var(--font-narrator);
		font-variant-caps: all-small-caps;
		letter-spacing: 0.06em;
		font-size: 1.05rem;
		color: var(--accent);
	}

	.heading small,
	.told small {
		color: var(--muted);
		font-size: 0.8rem;
	}

	.said {
		display: grid;
		gap: 0.2rem;
		min-width: 0;
	}

	.who {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.8rem;
		font-weight: 650;
		color: var(--muted);
	}

	.bubble {
		margin: 0;
		padding: 0.5rem 0.75rem;
		border-radius: 4px 14px 14px 14px;
		background: var(--surface-raised);
		border: 1px solid var(--border);
		line-height: 1.4;
	}

	.speech .bubble::before {
		content: '“';
		color: var(--accent);
		font-weight: 700;
		margin-right: 0.1rem;
	}

	.speech .bubble::after {
		content: '”';
		color: var(--accent);
		font-weight: 700;
		margin-left: 0.1rem;
	}

	/* A thought is never a bubble: a dashed, tinted cloud with a lock. */
	.thought .bubble {
		background: color-mix(in srgb, var(--thought) 10%, transparent);
		border: 1px dashed color-mix(in srgb, var(--thought) 65%, transparent);
		border-radius: 16px;
		font-style: italic;
		color: color-mix(in srgb, var(--thought) 25%, var(--text));
	}

	.whisper .bubble {
		background: color-mix(in srgb, var(--accent-2) 10%, transparent);
		border-color: color-mix(in srgb, var(--accent-2) 45%, transparent);
	}

	.tag {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.75rem;
		font-weight: 500;
		padding: 0 0.45rem;
		border-radius: 999px;
	}

	.thought-tag {
		color: var(--thought);
		background: color-mix(in srgb, var(--thought) 14%, transparent);
	}

	.thought-tag svg {
		width: 0.75rem;
		height: 0.75rem;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.4;
	}

	.whisper-tag {
		color: var(--accent-2);
		background: color-mix(in srgb, var(--accent-2) 14%, transparent);
	}

	.told {
		display: grid;
		gap: 0.1rem;
		min-width: 0;
		padding-top: 0.1rem;
	}

	.reveal,
	.result {
		padding: 0.55rem 0.7rem;
		border-radius: 10px;
		background: var(--surface-raised);
		border-left: 3px solid var(--accent);
	}

	.result {
		border-left-color: var(--ok);
	}

	.highlight.action {
		padding: 0.45rem 0.6rem;
		border-radius: 10px;
		background: color-mix(in srgb, var(--danger) 9%, var(--surface-raised));
		border-left: 3px solid var(--danger);
	}

	.highlight {
		animation: arrive 900ms ease-out;
	}

	@keyframes arrive {
		from {
			box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 60%, transparent);
		}
		to {
			box-shadow: 0 0 0 2px transparent;
		}
	}

	.final,
	.showdown {
		display: grid;
		gap: 0.35rem;
		width: 100%;
	}

	.label {
		font-size: 0.75rem;
		font-weight: 650;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--muted);
	}

	.final ol {
		display: grid;
		gap: 0.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.final li {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		font-size: 0.9rem;
	}

	.final li.first {
		font-weight: 700;
		color: var(--accent);
	}

	.final .rank {
		width: 2.2rem;
		font-variant-numeric: tabular-nums;
		color: var(--muted);
	}

	.hand-row {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		grid-template-areas:
			'avatar who cards'
			'avatar kind won';
		align-items: center;
		column-gap: 0.45rem;
		padding: 0.3rem 0.4rem;
		border-radius: 8px;
		background: var(--surface);
	}

	.hand-row > :global(svg) {
		grid-area: avatar;
	}

	.hand-row.won {
		box-shadow: inset 3px 0 0 var(--ok);
	}

	.hand-who {
		grid-area: who;
		font-weight: 600;
		font-size: 0.875rem;
	}

	.hand-cards {
		grid-area: cards;
		display: flex;
		gap: 0.2rem;
	}

	.mini {
		padding: 0 0.25rem;
		border-radius: 4px;
		background: #f3ead8;
		color: #1d1a16;
		font-size: 0.8rem;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.mini.red {
		color: #b3202e;
	}

	.hand-kind {
		grid-area: kind;
		font-size: 0.8rem;
		color: var(--muted);
	}

	.hand-won {
		grid-area: won;
		justify-self: end;
		font-size: 0.8rem;
		font-weight: 700;
		color: var(--ok);
		font-variant-numeric: tabular-nums;
	}

	.narration {
		margin: 0;
		font-family: var(--font-narrator);
		font-style: italic;
		color: color-mix(in srgb, var(--accent) 35%, var(--text));
	}

	.info {
		color: var(--muted);
		font-size: 0.8rem;
		padding-left: 0.2rem;
	}

	.bookkeeping {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.5rem 0.9rem;
		border-top: 1px solid var(--border);
		font-size: 0.8rem;
		color: var(--muted);
	}

	@media (prefers-reduced-motion: reduce) {
		.feed {
			scroll-behavior: auto;
		}

		.highlight {
			animation: none;
			outline: 1px solid color-mix(in srgb, var(--accent) 45%, transparent);
		}
	}
</style>
