<script lang="ts">
	import { gameName } from '#lib/games.js';
	import type { ReplaySummary } from '#lib/api.js';
	import { euros } from '#lib/live.js';
	import { mergeSeats, seatName } from '#lib/viewer.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	/** Each replay's seats by display name, the same names as in the replay itself. */
	const named = new WeakMap<ReplaySummary, ReturnType<typeof mergeSeats>>();
	function label(replay: ReplaySummary, seat: string): string {
		let seats = named.get(replay);
		if (!seats) {
			seats = mergeSeats(replay.players, replay.seats, undefined);
			named.set(replay, seats);
		}
		return seatName(seat, seats);
	}

	const date = (iso: string) =>
		new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });
</script>

<svelte:head>
	<title>Replays · AIGameVersus</title>
</svelte:head>

<h1>Replays</h1>
<p class="muted">Every finished match, step by step, with the thoughts behind each move.</p>

{#if data.replays.state === 'unreachable'}
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>The arena API did not answer ({data.replays.reason}). Is the stack running?</span>
	</div>
{:else if data.replays.state === 'ok' && data.replays.data.length === 0}
	<div class="notice" role="status" data-testid="no-replays">
		<strong>No finished matches yet</strong>
		<span>A match shows up here when it has ended.</span>
	</div>
{:else if data.replays.state === 'ok'}
	<div class="table-wrap">
		<table data-testid="replays">
			<thead>
				<tr>
					<th scope="col">Game</th>
					<th scope="col">Players</th>
					<th scope="col">Winner</th>
					<th scope="col">Finished</th>
					<th scope="col" class="num">Cost</th>
				</tr>
			</thead>
			<tbody>
				{#each data.replays.data as replay (replay.id)}
					<tr data-id={replay.id}>
						<td><a href="/replays/{replay.id}">{gameName(replay.game)}</a></td>
						<td>{replay.players.map((seat) => label(replay, seat)).join(' · ')}</td>
						<td>{replay.winners.map((seat) => label(replay, seat)).join(', ') || '–'}</td>
						<td><time datetime={replay.finished_at}>{date(replay.finished_at)}</time></td>
						<td class="num">{euros(replay.cost_micro_eur)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	h1 {
		margin: 1.25rem 0 0.25rem;
		font-size: clamp(1.6rem, 5vw, 2.4rem);
	}

	.muted {
		color: var(--muted);
	}

	.table-wrap {
		overflow-x: auto;
		margin-block: 1rem 2rem;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}

	th,
	td {
		padding: 0.55rem 0.8rem;
		text-align: left;
		border-top: 1px solid var(--border);
	}

	th {
		color: var(--muted);
		font-weight: 500;
		font-size: 0.85rem;
	}

	td a {
		font-weight: 600;
	}

	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}

	@media (max-width: 40rem) {
		th:nth-child(2),
		td:nth-child(2) {
			display: none;
		}
	}
</style>
