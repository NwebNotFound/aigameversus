<script lang="ts">
	import type { LiarsAnalytics } from '#lib/analytics/liars.js';
	import { scale } from '#lib/analytics/chart.js';
	import { seatHue } from '#lib/viewer.js';

	/**
	 * Cards left in each player's hand after each of their plays, over the match: a line per
	 * player in their colour, with a dot per play (red for a lie). Who is about to run out?
	 */
	let {
		data,
		names,
		colours
	}: { data: LiarsAnalytics; names: Record<string, string>; colours: Record<string, string> } =
		$props();

	const plays = $derived(data.moves.filter((m) => m.kind === 'play'));
	const W = 320;
	const H = 110;
	const x = $derived(scale(0, Math.max(1, data.moves.length - 1), 24, W - 6));
	const y = scale(0, 5, H - 14, 6);
	const colour = (player: string) => `oklch(0.75 0.12 ${seatHue(colours[player] ?? player)})`;

	function path(player: string): string {
		return plays
			.filter((m) => m.player === player)
			.map((m, i) => `${i ? 'L' : 'M'}${x(m.index).toFixed(1)},${y(m.cards_left ?? 0).toFixed(1)}`)
			.join(' ');
	}
</script>

<figure class="chart" data-testid="chart-cards">
	<figcaption>Cards left <small>after each play</small></figcaption>
	<svg viewBox="0 0 {W} {H}" role="img" aria-label="Cards left in hand after each play, per player">
		{#each [0, 5] as tick (tick)}
			<line class="grid" x1="24" x2={W} y1={y(tick)} y2={y(tick)} />
			<text class="tick" x="18" y={y(tick) + 3} text-anchor="end">{tick}</text>
		{/each}
		{#each data.players as player (player)}
			<path d={path(player)} stroke={colour(player)} />
			{#each plays.filter((m) => m.player === player) as m (m.seq)}
				<circle
					cx={x(m.index)}
					cy={y(m.cards_left ?? 0)}
					r="3.2"
					fill={m.honest === false ? 'var(--danger)' : colour(player)}
				>
					<title>{names[player] ?? player}, round {m.round}: {m.cards_left} left</title>
				</circle>
			{/each}
		{/each}
	</svg>
	<ul class="legend">
		{#each data.players as player (player)}
			<li><i style="background: {colour(player)}"></i>{names[player] ?? player}</li>
		{/each}
	</ul>
</figure>

<style>
	svg {
		display: block;
		width: 100%;
		height: auto;
	}

	path {
		fill: none;
		stroke-width: 2;
		stroke-linejoin: round;
		opacity: 0.85;
	}

	.grid {
		stroke: var(--border);
	}

	.tick {
		font-size: 10px;
		fill: var(--muted);
	}
</style>
