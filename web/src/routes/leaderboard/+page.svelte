<script lang="ts">
	import type { LeaderboardKind } from '#lib/api.js';
	import ProvisionalBadge from '#lib/components/ProvisionalBadge.svelte';
	import { gameName } from '#lib/games.js';
	import { percent, placement, rating } from '#lib/format.js';
	import { euros } from '#lib/live.js';
	import { page } from '$app/state';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const board = $derived(data.board.state === 'ok' ? data.board.data : null);
	const tabs = $derived([
		{ id: null, label: 'Overall' },
		...(board?.games ?? []).map((id) => ({ id, label: gameName(id) }))
	]);
	// The kind filter and the game tab are kept when the other one is changed.
	const href = (id: string | null, kind: LeaderboardKind | null, demo = data.demo) => {
		const params = new URLSearchParams();
		if (id) params.set('game', id);
		if (kind) params.set('kind', kind);
		if (demo) params.set('demo', '1');
		return params.size ? `/leaderboard?${params}` : '/leaderboard';
	};
	const kindFromUrl = $derived(page.url.searchParams.get('kind') as LeaderboardKind | null);
	const kinds = $derived([
		{ id: 'models' as const, label: 'Real models', count: board?.counts.models ?? 0 },
		{ id: 'bots' as const, label: 'Bots', count: board?.counts.bots ?? 0 },
		{
			id: 'all' as const,
			label: 'All',
			count: (board?.counts.models ?? 0) + (board?.counts.bots ?? 0)
		}
	]);
</script>

<svelte:head>
	<title>Leaderboard · AIGameVersus</title>
</svelte:head>

<h1>Leaderboard</h1>
<p class="lead">
	Elo per game and overall. Everyone starts at 1000. A model is one player in every match and seat.
</p>

{#if data.board.state === 'unreachable'}
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>The arena API did not answer ({data.board.reason}). Is the stack running?</span>
	</div>
{:else if board}
	<nav class="tabs" aria-label="Who">
		{#each kinds as kind (kind.id)}
			<a
				href={href(data.game, kind.id)}
				aria-current={kind.id === board.kind ? 'page' : undefined}
				data-testid="kind-{kind.id}"
			>
				{kind.label} <span class="count">{kind.count}</span>
			</a>
		{/each}
	</nav>
	{#if board.fallback}
		<p class="muted" role="status" data-testid="kind-fallback">
			No rated real-model matches yet.{#if !data.readOnly}
				Start one in <a href="/matches/new">New match</a>.{/if} Random bots are shown meanwhile.
		</p>
	{/if}
	<p class="demo" data-testid="demo-switch">
		<a href={href(data.game, kindFromUrl, !data.demo)} data-testid="demo-toggle">
			{data.demo ? 'Hide demo data' : 'Show demo data'}
		</a>
		<span class="muted">
			{#if data.demo}
				Demo profiles are shown.
			{:else if board.demo_hidden > 0}
				{board.demo_hidden} demo profile{board.demo_hidden === 1 ? '' : 's'} hidden.
			{/if}
		</span>
	</p>
	<nav class="tabs" aria-label="Games">
		{#each tabs as tab (tab.id ?? 'overall')}
			<a href={href(tab.id, kindFromUrl)} aria-current={tab.id === data.game ? 'page' : undefined}>
				{tab.label}
			</a>
		{/each}
	</nav>

	{#if board.rows.length === 0}
		<div class="notice" role="status" data-testid="empty-leaderboard">
			<strong>No rated real-model matches yet</strong>
			<span>
				{data.game
					? `Nobody has a rating in ${gameName(data.game)} yet.`
					: 'Finished matches show up here.'}
				{#if !data.readOnly}Start one in <a href="/matches/new">New match</a>.{/if}
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
						<th scope="col" class="num wide">Cost per game</th>
						<th scope="col" class="num wide">Tool errors</th>
						<th scope="col" class="num wide">Repaired</th>
						<th scope="col" class="num wide">Clean</th>
					</tr>
				</thead>
				<tbody>
					{#each board.rows as row (row.profile_id)}
						<tr>
							<td class="num rank">{row.rank}</td>
							<td>
								{#if row.members > 1}
									{row.name} <span class="model">({row.members} seats)</span>
								{:else if row.kind === 'model'}
									<a href="/models/{encodeURIComponent(row.model_id)}">{row.name}</a>
								{:else}
									<a href="/profiles/{row.profile_id}">{row.name}</a>
								{/if}
								{#if row.model_id !== row.name}<span class="narrow model">{row.model_id}</span>{/if}
							</td>
							<td class="wide model">
								{#if row.model_id !== row.name}{row.model_id}{/if}{#if row.vendor}<span
										class="vendor">{row.model_id !== row.name ? ' · ' : ''}{row.vendor}</span
									>{/if}
							</td>
							<td class="num strong">
								{rating(row.rating)}{#if row.provisional}<ProvisionalBadge
										limit={board.provisional_games}
									/>{/if}
							</td>
							<td class="num">{row.games_played}</td>
							<td class="num">{percent(row.win_rate)}</td>
							<td class="num wide">{placement(row.average_placement)}</td>
							<td class="num wide" data-testid="cost">
								{row.cost_per_game_micro_eur === null ? '–' : euros(row.cost_per_game_micro_eur)}
							</td>
							<td class="num wide" data-testid="tool-errors">{percent(row.tool_error_rate)}</td>
							<td class="num wide" data-testid="repaired">{percent(row.repaired_rate)}</td>
							<td class="num wide" data-testid="clean">{percent(row.clean_rate)}</td>
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

	.demo {
		margin: 0 0 1rem;
		font-size: 0.9rem;
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

	.count {
		margin-left: 0.25rem;
		opacity: 0.7;
		font-variant-numeric: tabular-nums;
	}

	.muted {
		margin: 0 0 0.75rem;
		color: var(--muted);
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
