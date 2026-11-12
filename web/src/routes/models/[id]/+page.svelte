<script lang="ts">
	import ProvisionalBadge from '#lib/components/ProvisionalBadge.svelte';
	import { gameName } from '#lib/games.js';
	import { percent, placement, rating, signed, statLabel, statValue } from '#lib/format.js';
	import { euros } from '#lib/live.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const page = $derived(data.result.state === 'ok' ? data.result.data : null);
	const name = $derived(page?.model?.id ?? 'Model');
	const gameStats = $derived(
		data.stats?.state === 'ok' ? data.stats.data.games.filter((g) => g.stats !== null) : []
	);
	const cost = (micro: number | null) => (micro === null ? '–' : euros(micro));
	// The same text on the server and in the browser: UTC, to the minute.
	const when = (iso: string) => `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
</script>

<svelte:head>
	<title>{name} · AIGameVersus</title>
</svelte:head>

<a class="back" href="/leaderboard">← Leaderboard</a>

{#if data.result.state === 'unreachable'}
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>The arena API did not answer ({data.result.reason}). Is the stack running?</span>
	</div>
{:else if page}
	<header class="head">
		<h1>{name}</h1>
		{#if page.model}
			<p class="model" data-testid="model-info">
				{page.model.provider_model}{page.model.vendor ? ` · ${page.model.vendor}` : ''} · ${page
					.model.input_usd_per_mtok} in / ${page.model.output_usd_per_mtok} out per million tokens
			</p>
		{/if}
	</header>

	{#if page.overall === null}
		<div class="notice" role="status" data-testid="not-played">
			<strong>Not played yet</strong>
			<span>No rated match has this model yet.</span>
		</div>
	{:else}
		<section aria-label="Summary" class="stats" data-testid="summary">
			<div>
				<span class="value">{rating(page.overall.rating)}</span><span class="label"
					>Overall rating{#if page.overall.provisional}<ProvisionalBadge
							limit={page.provisional_games}
						/>{/if}</span
				>
			</div>
			<div>
				<span class="value">{page.overall.games_played}</span><span class="label">Games</span>
			</div>
			<div>
				<span class="value">{percent(page.overall.win_rate)}</span><span class="label"
					>Win rate</span
				>
			</div>
			<div>
				<span class="value">{placement(page.overall.average_placement)}</span><span class="label"
					>Avg place</span
				>
			</div>
			<div>
				<span class="value" data-testid="cost-per-game"
					>{cost(page.usage.cost_per_game_micro_eur)}</span
				><span class="label">Cost per game</span>
			</div>
			<div>
				<span class="value" data-testid="tool-errors">{percent(page.usage.tool_error_rate)}</span
				><span class="label">Tool errors</span>
			</div>
			<div>
				<span class="value" data-testid="repaired">{percent(page.usage.repaired_rate)}</span><span
					class="label">Repaired</span
				>
			</div>
			<div>
				<span class="value" data-testid="clean">{percent(page.usage.clean_rate)}</span><span
					class="label">Clean</span
				>
			</div>
		</section>

		<section aria-labelledby="per-game">
			<h2 id="per-game">Per game</h2>
			<div class="table-wrap">
				<table data-testid="model-games">
					<thead>
						<tr>
							<th scope="col">Game</th>
							<th scope="col" class="num">Rating</th>
							<th scope="col" class="num">Games</th>
							<th scope="col" class="num">Win rate</th>
							<th scope="col" class="num">Avg place</th>
							<th scope="col" class="num">Cost per game</th>
							<th scope="col" class="num">Tool errors</th>
							<th scope="col" class="num">Repaired</th>
							<th scope="col" class="num">Clean</th>
						</tr>
					</thead>
					<tbody>
						{#each page.games as game (game.game_id)}
							<tr data-game={game.game_id}>
								<td>{gameName(game.game_id)}</td>
								<td class="num strong">
									{rating(game.rating)}{#if game.provisional}<ProvisionalBadge
											limit={page.provisional_games}
										/>{/if}
								</td>
								<td class="num">{game.games_played}</td>
								<td class="num">{percent(game.win_rate)}</td>
								<td class="num">{placement(game.average_placement)}</td>
								<td class="num">{cost(game.usage.cost_per_game_micro_eur)}</td>
								<td class="num">{percent(game.usage.tool_error_rate)}</td>
								<td class="num">{percent(game.usage.repaired_rate)}</td>
								<td class="num">{percent(game.usage.clean_rate)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>

		<section aria-labelledby="recent">
			<h2 id="recent">Recent matches</h2>
			<ul class="matches" data-testid="model-matches">
				{#each page.recent_matches as match (match.match_id)}
					<li>
						<span>{gameName(match.game_id)}</span>
						<span class="muted" data-testid="match-date">{when(match.played_at)}</span>
						<span>place {match.rank} of {match.players}</span>
						<span class:up={match.rating_change > 0} class:down={match.rating_change < 0}>
							{signed(match.rating_change)}
						</span>
						<span class="links">
							<a href="/replays/{match.match_id}">Replay</a>
							<a href="/matches/{match.match_id}">Match</a>
						</span>
					</li>
				{/each}
			</ul>
		</section>

		<section aria-labelledby="game-stats">
			<h2 id="game-stats">Game statistics</h2>
			{#if data.stats?.state === 'unreachable'}
				<p class="muted">The statistics could not be loaded ({data.stats.reason}).</p>
			{:else if gameStats.length === 0}
				<p class="muted" data-testid="no-game-stats">
					No statistics yet: they come from rated matches of Liar's Deck, Poker and Werewolf.
				</p>
			{:else}
				<div class="game-stats">
					{#each gameStats as game (game.game_id)}
						<table data-testid="game-stats" data-game={game.game_id}>
							<caption
								>{gameName(game.game_id)} · {game.matches}
								{game.matches === 1 ? 'match' : 'matches'}</caption
							>
							<tbody>
								{#each Object.entries(game.stats ?? {}).filter(([field]) => field !== 'matches') as [field, value] (field)}
									<tr>
										<th scope="row">{statLabel(field)}</th>
										<td>{statValue(field, value)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					{/each}
				</div>
			{/if}
		</section>
	{/if}

	{#if page.personalities.length > 0}
		<section aria-labelledby="personalities">
			<h2 id="personalities">With a personality</h2>
			<ul class="matches" data-testid="personalities">
				{#each page.personalities as other (other.profile_id)}
					<li><a href="/profiles/{other.profile_id}">{other.personality_id}</a></li>
				{/each}
			</ul>
		</section>
	{/if}
{/if}

<style>
	.back {
		display: inline-block;
		margin-top: 1rem;
		color: var(--muted);
	}

	h1 {
		margin: 0.5rem 0 0;
		font-size: clamp(1.8rem, 6vw, 2.6rem);
	}

	h2 {
		margin: 2rem 0 0.75rem;
		font-size: 0.85rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
	}

	.model,
	.muted {
		margin: 0.25rem 0 0;
		color: var(--muted);
	}

	.stats {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
		gap: 0.75rem;
		margin-top: 1.25rem;
	}

	.stats div {
		display: grid;
		gap: 0.2rem;
		padding: 0.9rem 1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.value {
		font-size: 1.5rem;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.label {
		color: var(--muted);
		font-size: 0.8rem;
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
		padding: 0.6rem 0.9rem;
		text-align: left;
		border-bottom: 1px solid var(--border);
	}

	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}

	.strong {
		font-weight: 700;
		color: var(--accent);
	}

	.matches {
		display: grid;
		gap: 0.4rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.matches li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.25rem;
		padding: 0.6rem 0.9rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.links {
		margin-left: auto;
		display: flex;
		gap: 0.75rem;
	}

	.up {
		color: #7ad69a;
	}

	.down {
		color: var(--danger);
	}

	.game-stats {
		display: flex;
		flex-wrap: wrap;
		gap: 1rem;
	}

	.game-stats table {
		width: auto;
		min-width: 14rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}

	caption {
		text-align: left;
		padding: 0.4rem 0.9rem;
		color: var(--muted);
		font-size: 0.85rem;
	}
</style>
