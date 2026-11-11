<script lang="ts">
	import type { MatchEvent } from '#lib/api.js';
	import { hidden } from '#lib/live.js';
	import LiarsDeckTable from './LiarsDeckTable.svelte';
	import PokerTable from './PokerTable.svelte';
	import WerewolfCircle from './WerewolfCircle.svelte';

	/**
	 * The generic board: any game's render_spec as a header of fields and one card
	 * per seat. Game tables with their own drawing replace it per layout later.
	 */
	let {
		spec,
		spoilers,
		events = [],
		names = {},
		colours = {}
	}: {
		spec: Record<string, unknown> | null;
		spoilers: boolean;
		events?: MatchEvent[];
		/** Seat id to the name shown at the seat; the seat id when missing. */
		names?: Record<string, string>;
		/** Seat id to the key its avatar colour comes from (the model, else the seat). */
		colours?: Record<string, string>;
	} = $props();

	type Seat = Record<string, unknown> & { player: string };

	const seats = $derived(
		Array.isArray(spec?.seats) && spec.seats.every((s) => typeof s?.player === 'string')
			? (spec.seats as Seat[])
			: null
	);
	const header = $derived(
		spec ? Object.entries(spec).filter(([key]) => !['layout', 'seats', 'turn'].includes(key)) : []
	);
	/** The Liar's Deck table needs seats with hands and revolvers; anything else gets the generic board. */
	function isCardTable(spec: Record<string, unknown>): boolean {
		return (
			Array.isArray(spec.seats) &&
			spec.seats.every(
				(s) =>
					typeof s?.player === 'string' &&
					Array.isArray(s.hand) &&
					typeof s.trigger_pulls === 'number' &&
					typeof s.chambers === 'number'
			)
		);
	}

	/** The Poker table needs seats with a stack and hole cards, and a board. */
	function isPokerTable(spec: Record<string, unknown>): boolean {
		return (
			Array.isArray(spec.board) &&
			Array.isArray(spec.seats) &&
			spec.seats.every(
				(s) =>
					typeof s?.player === 'string' && typeof s.stack === 'number' && Array.isArray(s.cards)
			)
		);
	}

	/** The Werewolf circle needs seats with an alive flag; the role may be missing. */
	function isPlayerCircle(spec: Record<string, unknown>): boolean {
		return (
			Array.isArray(spec.seats) &&
			spec.seats.every((s) => typeof s?.player === 'string' && typeof s.alive === 'boolean')
		);
	}

	const SEAT_FLAGS = ['player', 'alive', 'folded'];

	const label = (key: string) => key.replaceAll('_', ' ');

	function show(value: unknown): string {
		if (value === null || value === undefined) return '–';
		if (Array.isArray(value)) return value.length ? value.map(show).join(' ') : '–';
		if (typeof value === 'object') {
			return Object.entries(value)
				.map(([k, v]) => `${label(k)}: ${hidden(k, spoilers) ? 'hidden' : show(v)}`)
				.join(', ');
		}
		return String(value);
	}
</script>

{#if spec === null}
	<div class="notice" role="status" data-testid="no-board">
		<strong>No board for this game yet</strong>
		<span>The events in the other columns show the whole match.</span>
	</div>
{:else if spec.layout === 'card_table' && isCardTable(spec)}
	<LiarsDeckTable {spec} {spoilers} {names} {colours} />
{:else if spec.layout === 'poker_table' && isPokerTable(spec)}
	<PokerTable {spec} {spoilers} {events} {names} {colours} />
{:else if spec.layout === 'player_circle' && isPlayerCircle(spec)}
	<WerewolfCircle {spec} {spoilers} {events} {names} {colours} />
{:else}
	<div class="board" data-testid="board" data-layout={spec.layout}>
		{#if header.length}
			<dl class="header">
				{#each header as [key, value] (key)}
					<div>
						<dt>{label(key)}</dt>
						<dd>{hidden(key, spoilers) ? 'hidden' : show(value)}</dd>
					</div>
				{/each}
			</dl>
		{/if}

		{#if seats}
			<ul class="seats">
				{#each seats as seat (seat.player)}
					<li
						data-testid="seat"
						class:out={seat.alive === false || seat.folded === true}
						class:turn={seat.player === spec.turn}
					>
						<strong>{names[seat.player] ?? seat.player}</strong>
						{#if seat.player === spec.turn}<span class="tag act">to act</span>{/if}
						{#if seat.alive === false}<span class="tag">out</span>{/if}
						{#if seat.folded === true}<span class="tag">folded</span>{/if}
						<dl>
							{#each Object.entries(seat).filter(([k]) => !SEAT_FLAGS.includes(k)) as [key, value] (key)}
								<div>
									<dt>{label(key)}</dt>
									{#if hidden(key, spoilers)}
										<dd class="secret" data-testid="secret">hidden</dd>
									{:else}
										<dd>{show(value)}</dd>
									{/if}
								</div>
							{/each}
						</dl>
					</li>
				{/each}
			</ul>
		{:else}
			<pre data-testid="board-json">{JSON.stringify(spec, null, 2)}</pre>
		{/if}
	</div>
{/if}

<style>
	.board {
		display: grid;
		gap: 0.75rem;
	}

	dl {
		margin: 0;
	}

	dt {
		color: var(--muted);
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	dd {
		margin: 0;
		overflow-wrap: anywhere;
	}

	.header {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.25rem;
	}

	.seats {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
		gap: 0.5rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.seats li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.5rem;
		padding: 0.6rem 0.75rem;
		border-radius: var(--radius);
		background: var(--surface-raised);
		border: 1px solid var(--border);
	}

	.seats li dl {
		flex-basis: 100%;
		display: grid;
		gap: 0.25rem;
	}

	.seats li.turn {
		border-color: var(--accent);
	}

	.seats li.out {
		opacity: 0.55;
	}

	.tag {
		font-size: 0.7rem;
		padding: 0 0.45rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
	}

	.act {
		color: var(--accent);
		border-color: var(--accent);
	}

	.secret {
		color: var(--muted);
		font-style: italic;
	}

	pre {
		margin: 0;
		overflow-x: auto;
		font-size: 0.8rem;
	}
</style>
