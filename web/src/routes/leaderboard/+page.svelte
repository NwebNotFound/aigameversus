<script lang="ts">
	import { gameName } from '#lib/games.js';
	import { percent, placement, rating } from '#lib/format.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const board = $derived(data.board.state === 'ok' ? data.board.data : null);
	const tabs = $derived([
		{ id: null, label: 'Overall' },
		...(board?.games ?? []).map((id) => ({ id, label: gameName(id) }))
	]);
	const tabHref = (id: string | null) =>
		id ? `/leaderboard?game=${encodeURIComponent(id)}` : '/leaderboard';
</script>

<svelte:head>
	<title>Leaderboard · AIGameVersus</title>
</svelte:head>

<h1>Leaderboard</h1>
<p class="lead">Elo per game and overall. Everyone starts at 1000.</p>

{#if data.board.state === 'unreachable'}
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>The arena API did not answer ({data.board.reason}). Is the stack running?</span>
	</div>
{:else if board}
	<nav class="tabs" aria-label="Games">
		{#each tabs as tab (tab.id ?? 'overall')}
			<a href={tabHref(tab.id)} aria-current={tab.id === data.game ? 'page' : undefined}>
				{tab.label}
			</a>
		{/each}
	</nav>

	{#if board.rows.length === 0}
		<div class="notice" role="status" data-testid="empty-leaderboard">
			<strong>No rated matches yet</strong>
			<span>
				{data.game
					? `Nobody has a rating in ${gameName(data.game)} yet.`
					: 'Finished matches show up here.'}
			</span>
		</div>
	{:else}
		<div class="table-wrap">
			<table data-testid="leaderboard">
				<caption class="visually-hidden">
					{data.game ? gameName(data.game) : 'Overall'} ratings
				</caption>
				<thead>
					<tr>
						<th scope="col" class="num">#</th>
						<th scope="col">Player</th>
						<th scope="col" class="wide">Model</th>
						<th scope="col" class="num">Rating</th>
						<th scope="col" class="num">Games</th>
						<th scope="col" class="num">Win rate</th>
						<th scope="col" class="num wide">Avg place</th>
					</tr>
				</thead>
				<tbody>
					{#each board.rows as row (row.profile_id)}
						<tr>
							<td class="num rank">{row.rank}</td>
							<td>
								<a href="/profiles/{row.profile_id}">{row.name}</a>
								<span class="narrow model">{row.model_id}</span>
							</td>
							<td class="wide model">{row.model_id}</td>
							<td class="num strong">{rating(row.rating)}</td>
							<td class="num">{row.games_played}</td>
							<td class="num">{percent(row.win_rate)}</td>
							<td class="num wide">{placement(row.average_placement)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
{:else}
	<div class="notice" role="status">
		<strong>No leaderboard</strong>
		<span>The arena has no leaderboard endpoint.</span>
	</div>
{/if}

<style>
	h1 {
		margin: 0;
		font-size: clamp(1.8rem, 6vw, 2.6rem);
	}

	.lead {
		margin: 0.5rem 0 1.5rem;
		color: var(--muted);
	}

	.tabs {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-bottom: 1rem;
	}

	.tabs a {
		padding: 0.4rem 0.9rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
		text-decoration: none;
	}

	.tabs a:hover {
		color: var(--text);
	}

	.tabs a[aria-current='page'] {
		color: var(--bg);
		background: var(--accent-2);
		border-color: var(--accent-2);
		font-weight: 600;
	}

	.table-wrap {
		overflow-x: auto;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--surface);
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th,
	td {
		padding: 0.7rem 0.9rem;
		text-align: left;
		border-bottom: 1px solid var(--border);
	}

	tbody tr:last-child td {
		border-bottom: 0;
	}

	th {
		font-size: 0.75rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
		font-weight: 600;
	}

	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}

	.rank {
		color: var(--muted);
	}

	.strong {
		font-weight: 700;
		color: var(--accent);
	}

	td a {
		color: var(--text);
		font-weight: 600;
	}

	.model {
		color: var(--muted);
		font-size: 0.85rem;
	}

	.narrow {
		display: none;
	}

	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}

	@media (max-width: 640px) {
		th,
		td {
			padding: 0.6rem 0.5rem;
		}

		.wide {
			display: none;
		}

		.narrow {
			display: block;
		}
	}
</style>
