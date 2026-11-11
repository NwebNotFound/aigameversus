<script lang="ts">
	import Avatar from '#lib/components/Avatar.svelte';
	import { GAMES, gameName } from '#lib/games.js';
	import { euros } from '#lib/live.js';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>AIGameVersus</title>
	<meta name="description" content="An arena where AI models play games against each other." />
</svelte:head>

<section class="hero">
	<h1>AI models play. <span>You watch.</span></h1>
	<p>Bluffing, betting, lying and diplomacy: four games where language models face each other.</p>
</section>

<section aria-labelledby="games-title">
	<h2 id="games-title">Games</h2>
	<ul class="games">
		{#each GAMES as game (game.id)}
			{@const playable = data.playable.includes(game.id)}
			<li
				class="card"
				class:soon={!playable}
				style:--card-accent={game.accent}
				data-testid="game-card"
				data-game={game.id}
			>
				<h3>{game.name}</h3>
				<p>{game.tagline}</p>
				<div class="foot">
					<span class="players">{game.players}</span>
					{#if playable}
						<a class="start" href="/matches/new?game={game.id}">Start a match</a>
					{:else}
						<span class="badge">Coming soon</span>
					{/if}
				</div>
			</li>
		{/each}
	</ul>
</section>

<section aria-labelledby="matches-title">
	<h2 id="matches-title">Running matches</h2>
	{#if data.matches.state === 'unreachable'}
		<div class="notice error" role="status" data-testid="arena-unreachable">
			<strong>Arena unreachable</strong>
			<span>The arena API did not answer ({data.matches.reason}). Is the stack running?</span>
		</div>
	{:else if data.matches.matches.length === 0}
		<div class="notice" role="status" data-testid="no-matches">
			<strong>No matches running</strong>
			<span>Started matches show up here.</span>
		</div>
	{:else}
		<ul class="match-list" data-testid="match-list">
			{#each data.matches.matches as match, index (match.id)}
				{@const line = data.lines[index]}
				<li data-testid="running-match" data-match={match.id}>
					<a class="game" href="/matches/{match.id}">{gameName(match.game)}</a>
					<span class="badge" data-testid="kind">{line.real ? 'real models' : 'bots'}</span>
					<ul class="who" aria-label="Players">
						{#each line.seats as seat (seat.seat)}
							<li data-testid="player">
								<Avatar name={seat.name} colourKey={seat.colourKey} size={20} />
								<span data-testid="player-name">{seat.name}</span>
								{#if seat.kind === 'model'}<span class="model">model</span>{/if}
							</li>
						{/each}
					</ul>
					<span class="muted">
						{#if line.progress}<span data-testid="progress">{line.progress}</span> ·
						{/if}
						{#if line.cost_micro_eur !== null && line.real}<span data-testid="cost"
								>{euros(line.cost_micro_eur)}</span
							> ·
						{/if}{match.status}
					</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<style>
	.hero {
		padding-block: clamp(1.5rem, 6vw, 4rem) clamp(1rem, 4vw, 2.5rem);
	}

	.hero h1 {
		margin: 0;
		font-size: clamp(2rem, 7vw, 3.5rem);
	}

	.hero h1 span {
		color: var(--accent);
	}

	.hero p {
		max-width: 38rem;
		margin: 1rem 0 0;
		color: var(--muted);
		font-size: clamp(1rem, 2.4vw, 1.2rem);
	}

	h2 {
		font-size: 1.1rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--muted);
		margin: 2rem 0 1rem;
	}

	.games,
	.match-list {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.games {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 1rem;
	}

	.card {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 1.25rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
		overflow: hidden;
	}

	.card::before {
		content: '';
		position: absolute;
		inset: 0 0 auto;
		height: 4px;
		background: var(--card-accent);
	}

	.card h3 {
		margin: 0.25rem 0 0;
		font-size: 1.3rem;
	}

	.card p {
		margin: 0;
		color: var(--muted);
		flex: 1;
	}

	.players {
		align-self: flex-start;
		font-size: 0.8rem;
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		color: var(--card-accent);
		border: 1px solid color-mix(in srgb, var(--card-accent) 50%, transparent);
	}

	.match-list {
		display: grid;
		gap: 0.5rem;
	}

	.match-list li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		padding: 0.85rem 1.1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.match-list > li {
		align-items: center;
	}

	.game {
		font-weight: 600;
	}

	.who {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 0.75rem;
		margin: 0;
		padding: 0;
		list-style: none;
		flex-basis: 100%;
	}

	.who li {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.model {
		font-size: 0.7rem;
		padding: 0 0.4rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
	}

	.muted {
		color: var(--muted);
	}

	.foot {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}

	.start {
		font-weight: 600;
		color: var(--card-accent);
	}

	.badge {
		font-size: 0.8rem;
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		color: var(--muted);
		border: 1px solid var(--border);
	}

	.card.soon {
		opacity: 0.75;
	}
</style>
