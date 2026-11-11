<script lang="ts">
	import type { MatchEvent } from '#lib/api.js';
	import Board from '#lib/components/Board.svelte';
	import type { Lang } from '#lib/event-text.js';
	import { columnOf, describe, playersOf } from '#lib/live.js';

	/**
	 * The three columns of a match: the board, the public events and what
	 * happens behind the scenes (filterable by player). The live view and the
	 * replay player show a match through it.
	 */
	let {
		spec,
		spoilers,
		events,
		players,
		game,
		lang
	}: {
		spec: Record<string, unknown> | null;
		spoilers: boolean;
		events: MatchEvent[];
		players: string[];
		/** Game id, for the sentences of its events. */
		game: string;
		lang: Lang;
	} = $props();

	let player = $state('all');
	/** Show every event as stored (type and data) instead of a sentence. */
	let raw = $state(false);

	const publicLines = $derived(events.filter((e) => columnOf(e) === 'public').toReversed());
	const behindLines = $derived(
		events
			.filter((e) => columnOf(e) === 'behind')
			.filter((e) => player === 'all' || playersOf(e).includes(player))
			.toReversed()
	);
</script>

<div class="columns">
	<section aria-labelledby="board-title">
		<h2 id="board-title">Board</h2>
		<Board {spec} {spoilers} {events} />
	</section>

	<section aria-labelledby="public-title">
		<div class="feed-head">
			<h2 id="public-title">Public</h2>
			<label class="raw">
				<input type="checkbox" bind:checked={raw} />
				Raw events
			</label>
		</div>
		{#if publicLines.length === 0}
			<p class="muted">Nothing public yet.</p>
		{/if}
		<ol class="feed" data-testid="public-feed">
			{#each publicLines as event (event.seq)}
				{@render line(event)}
			{/each}
		</ol>
	</section>

	<section aria-labelledby="behind-title">
		<h2 id="behind-title">Behind the scenes</h2>
		{#if spoilers}
			<label class="filter">
				Player
				<select bind:value={player}>
					<option value="all">All players</option>
					{#each players as name (name)}
						<option value={name}>{name}</option>
					{/each}
				</select>
			</label>
			<ol class="feed" data-testid="behind-feed">
				{#each behindLines as event (event.seq)}
					{@render line(event)}
				{/each}
			</ol>
		{:else}
			<div class="notice" role="status" data-testid="spoilers-off">
				<strong>Spoilers off</strong>
				<span>Thoughts, hands and private messages stay hidden, so you can guess along.</span>
			</div>
		{/if}
	</section>
</div>

{#snippet line(event: MatchEvent)}
	{@const shown = describe(event, game, lang)}
	<li
		data-seq={event.seq}
		data-kind={shown.kind}
		data-players={playersOf(event).join(' ')}
		data-raw={shown.kind === 'event' && !shown.sentence}
	>
		{#if shown.kind === 'message'}
			<strong>{shown.player}</strong>
			<q>{shown.text}</q>
		{:else if shown.kind === 'thought'}
			<strong>{shown.player}</strong> <span class="muted">thinks</span>
			<em>{shown.text}</em>
		{:else if shown.kind === 'narration'}
			<span class="narration">{shown.text}</span>
		{:else if shown.sentence && !raw}
			<span class="sentence">{shown.sentence}</span>
		{:else}
			{#if shown.player}<strong>{shown.player}</strong>{/if}
			<span>{shown.title}</span>
			{#if shown.details}<small class="muted">{shown.details}</small>{/if}
		{/if}
	</li>
{/snippet}

<style>
	h2 {
		font-size: 0.95rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--muted);
		margin: 0 0 0.75rem;
	}

	.columns {
		display: grid;
		gap: var(--gap);
		padding-block: 1rem 2rem;
	}

	.columns > section {
		min-width: 0;
		padding: 1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	@media (min-width: 64rem) {
		.columns {
			grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, 1fr);
			align-items: start;
		}

		.feed {
			max-height: 70vh;
			overflow-y: auto;
		}
	}

	.feed {
		display: grid;
		gap: 0.4rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.feed li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.15rem 0.45rem;
		padding: 0.45rem 0.6rem;
		border-radius: 8px;
		background: var(--surface-raised);
		overflow-wrap: anywhere;
	}

	.feed li[data-kind='message'] {
		border-left: 3px solid var(--accent-2);
	}

	.feed li[data-kind='thought'] {
		border-left: 3px solid var(--accent);
	}

	.feed small {
		flex-basis: 100%;
	}

	.narration {
		font-style: italic;
	}

	.muted {
		color: var(--muted);
	}

	.filter {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		margin-bottom: 0.75rem;
	}

	select {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.35rem 0.8rem;
		min-height: 2.25rem;
	}

	.feed-head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.25rem 1rem;
	}

	.raw {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.8rem;
		color: var(--muted);
		margin-bottom: 0.75rem;
	}
</style>
