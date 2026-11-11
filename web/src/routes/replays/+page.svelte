<script lang="ts">
	import { page } from '$app/state';
	import { gameName } from '#lib/games.js';
	import { euros } from '#lib/live.js';
	import { playerLabel, playerName, realModels } from '#lib/players.js';
	import { filterReplays, KINDS } from '#lib/replay-list.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const all = $derived(data.replays.state === 'ok' ? data.replays.data : []);
	const games = $derived([...new Set(all.map((r) => r.game))].sort());
	const game = $derived(page.url.searchParams.get('game') ?? '');
	const kind = $derived(page.url.searchParams.get('kind') ?? '');
	const shown = $derived(filterReplays(all, game, kind));

	const date = (iso: string) =>
		new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' });

	function duration(from: string, to: string): string {
		const seconds = Math.max(0, Math.round((Date.parse(to) - Date.parse(from)) / 1000));
		if (seconds < 60) return `${seconds} s`;
		const minutes = Math.round(seconds / 60);
		return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
	}
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
	<form class="filters" method="GET" data-sveltekit-keepfocus>
		<label>
			Game
			<select name="game" value={game} onchange={(e) => e.currentTarget.form?.requestSubmit()}>
				<option value="">All games</option>
				{#each games as id (id)}
					<option value={id}>{gameName(id)}</option>
				{/each}
			</select>
		</label>
		<label>
			Players
			<select name="kind" value={kind} onchange={(e) => e.currentTarget.form?.requestSubmit()}>
				{#each KINDS as option (option.id)}
					<option value={option.id}>{option.label}</option>
				{/each}
			</select>
		</label>
		<noscript><button type="submit">Filter</button></noscript>
	</form>
	{#if shown.length === 0}
		<p class="muted" data-testid="no-match-for-filter">No replay matches these filters.</p>
	{/if}
	<div class="table-wrap">
		<table data-testid="replays">
			<thead>
				<tr>
					<th scope="col">Game</th>
					<th scope="col">Players</th>
					<th scope="col">Winner</th>
					<th scope="col">Finished</th>
					<th scope="col">Length</th>
					<th scope="col" class="num">Cost</th>
				</tr>
			</thead>
			<tbody>
				{#each shown as replay (replay.id)}
					{@const real = realModels(replay.seats)}
					<tr data-id={replay.id} data-real={real}>
						<td>
							<a href="/replays/{replay.id}">{gameName(replay.game)}</a>
							<span class="badge" class:real data-testid="kind"
								>{real ? 'real models' : 'bots'}</span
							>
						</td>
						<td>{replay.players.map((seat) => playerLabel(seat, replay.seats)).join(' · ')}</td>
						<td class="winner">
							{replay.winners.map((seat) => playerName(seat, replay.seats)).join(', ') || '–'}
						</td>
						<td><time datetime={replay.finished_at}>{date(replay.finished_at)}</time></td>
						<td>{duration(replay.started_at, replay.finished_at)}</td>
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

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.25rem;
		margin-top: 1rem;
	}

	.filters label {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}

	.filters select,
	.filters button {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.3rem 0.6rem;
	}

	.badge {
		margin-left: 0.4rem;
		font-size: 0.7rem;
		padding: 0.05rem 0.45rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
		white-space: nowrap;
	}

	.badge.real {
		color: var(--accent);
		border-color: var(--accent);
	}

	.winner {
		font-weight: 600;
	}
</style>
