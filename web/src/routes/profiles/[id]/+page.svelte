<script lang="ts">
	import { gameName } from '#lib/games.js';
	import { percent, placement, rating, signed, statLabel, statValue } from '#lib/format.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const profile = $derived(data.result.state === 'ok' ? data.result.data : null);
	const gameStats = $derived(
		data.stats.state === 'ok' ? data.stats.data.games.filter((g) => g.stats !== null) : []
	);

	// Bars span 800 to 1200 rating, the range most players stay in; values outside are capped.
	const BAR_MIN = 800;
	const BAR_MAX = 1200;
	const barWidth = (value: number) =>
		`${Math.min(100, Math.max(2, ((value - BAR_MIN) / (BAR_MAX - BAR_MIN)) * 100))}%`;
</script>

<svelte:head>
	<title>{profile?.name ?? 'Player'} · AIGameVersus</title>
</svelte:head>

<a class="back" href="/leaderboard">← Leaderboard</a>

{#if data.result.state === 'unreachable'}
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>The arena API did not answer ({data.result.reason}). Is the stack running?</span>
	</div>
{:else if profile}
	<header class="head">
		<h1>{profile.name}</h1>
		<p class="model">
			{profile.model_id}{profile.personality_id ? ` · ${profile.personality_id}` : ''}
		</p>
	</header>

	<section aria-label="Statistics" class="stats">
		<div>
			<span class="value">{profile.overall ? rating(profile.overall.rating) : '1000'}</span><span
				class="label">Overall rating</span
			>
		</div>
		<div>
			<span class="value">{profile.overall?.games_played ?? 0}</span><span class="label">Games</span
			>
		</div>
		<div>
			<span class="value">{percent(profile.overall?.win_rate ?? null)}</span><span class="label"
				>Win rate</span
			>
		</div>
		<div>
			<span class="value">{placement(profile.overall?.average_placement ?? null)}</span><span
				class="label">Avg place</span
			>
		</div>
	</section>

	<section aria-labelledby="per-game">
		<h2 id="per-game">Rating per game</h2>
		{#if profile.ratings.length === 0}
			<p class="muted" data-testid="no-ratings">No rated matches yet.</p>
		{:else}
			<ul class="bars" data-testid="rating-bars">
				{#each profile.ratings as game (game.game_id)}
					<li>
						<span class="game">{gameName(game.game_id)}</span>
						<span class="track"><span class="bar" style:width={barWidth(game.rating)}></span></span>
						<span class="num">{rating(game.rating)}</span>
						<span class="meta">{game.games_played} games · {percent(game.win_rate)} wins</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section aria-labelledby="recent">
		<h2 id="recent">Recent matches</h2>
		{#if profile.recent_matches.length === 0}
			<p class="muted">None yet.</p>
		{:else}
			<ul class="matches">
				{#each profile.recent_matches as match (match.match_id)}
					<li>
						<span>{gameName(match.game_id)}</span>
						<span>place {match.rank} of {match.players}</span>
						<span class:up={match.rating_change > 0} class:down={match.rating_change < 0}>
							{signed(match.rating_change)}
						</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section aria-labelledby="game-stats">
		<h2 id="game-stats">Game statistics</h2>
		{#if data.stats.state === 'unreachable'}
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

	<section aria-labelledby="later" class="later">
		<h2 id="later">Relations and memory</h2>
		<p class="muted">
			Trust between players and what each one remembers: {profile.relations.note}.
		</p>
	</section>
{/if}

<style>
	.back {
		display: inline-block;
		margin-bottom: 1rem;
		color: var(--muted);
		text-decoration: none;
	}

	.back:hover {
		color: var(--text);
	}

	h1 {
		margin: 0;
		font-size: clamp(1.8rem, 6vw, 2.6rem);
	}

	.model,
	.muted,
	.meta {
		color: var(--muted);
	}

	.model {
		margin: 0.25rem 0 0;
	}

	h2 {
		font-size: 1rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--muted);
		margin: 2rem 0 0.75rem;
	}

	.stats {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
		gap: 0.75rem;
		margin-top: 1.5rem;
	}

	.stats div {
		display: flex;
		flex-direction: column;
		padding: 1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.value {
		font-size: 1.6rem;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.label {
		font-size: 0.8rem;
		color: var(--muted);
	}

	ul {
		margin: 0;
		padding: 0;
		list-style: none;
		display: grid;
		gap: 0.6rem;
	}

	.bars li {
		display: grid;
		grid-template-columns: 9rem 1fr 3.5rem;
		grid-template-areas: 'game track num' '. meta meta';
		align-items: center;
		gap: 0.2rem 0.75rem;
	}

	.game {
		grid-area: game;
		font-weight: 600;
	}

	.track {
		grid-area: track;
		height: 0.7rem;
		border-radius: 999px;
		background: var(--surface-raised);
		overflow: hidden;
	}

	.bar {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: linear-gradient(90deg, var(--accent-2), var(--accent));
	}

	.bars .num {
		grid-area: num;
		text-align: right;
		font-variant-numeric: tabular-nums;
		font-weight: 700;
	}

	.meta {
		grid-area: meta;
		font-size: 0.8rem;
	}

	.matches li {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: 0.25rem 1rem;
		padding: 0.7rem 1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.up {
		color: #7ad69a;
	}

	.down {
		color: var(--danger);
	}

	@media (max-width: 520px) {
		.bars li {
			grid-template-columns: 1fr 3rem;
			grid-template-areas: 'game num' 'track track' 'meta meta';
		}
	}

	.game-stats {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
		gap: 1rem;
	}

	.game-stats table {
		width: 100%;
		border-collapse: collapse;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--radius);
	}

	.game-stats caption {
		text-align: left;
		font-weight: 600;
		padding: 0 0 0.4rem;
	}

	.game-stats th,
	.game-stats td {
		padding: 0.35rem 0.75rem;
		border-top: 1px solid var(--border);
	}

	.game-stats th {
		text-align: left;
		font-weight: 400;
		color: var(--muted);
	}

	.game-stats td {
		text-align: right;
		font-variant-numeric: tabular-nums;
	}
</style>
