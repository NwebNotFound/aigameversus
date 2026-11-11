<script lang="ts">
	import type { LiarsAnalytics } from '#lib/analytics/liars.js';
	import { niceMax, scale, seconds } from '#lib/analytics/chart.js';
	import { seatHue } from '#lib/viewer.js';

	/**
	 * Thinking time of every move (network time included, docs/METRICS.md), a bar each in
	 * the player's colour; slow outliers are outlined. Until the runner records it, this
	 * says so instead of drawing nothing.
	 */
	let {
		data,
		names,
		colours,
		slow,
		onjump
	}: {
		data: LiarsAnalytics;
		names: Record<string, string>;
		colours: Record<string, string>;
		slow: Set<number>;
		onjump?: (seq: number) => void;
	} = $props();

	const timed = $derived(data.moves.filter((m) => m.latency_ms !== null));
	const top = $derived(niceMax(Math.max(0, ...timed.map((m) => m.latency_ms ?? 0))));
	const H = 120;
	const BAR = 8;
	const width = $derived(Math.max(240, data.moves.length * (BAR + 3) + 40));
	const y = $derived(scale(0, top, H, 8));
	const colour = (player: string) => `oklch(0.75 0.12 ${seatHue(colours[player] ?? player)})`;
</script>

<figure class="chart" data-testid="chart-thinking">
	<figcaption>Thinking time <small>per move · outlined = unusually slow</small></figcaption>
	{#if timed.length === 0}
		<p class="empty" data-testid="thinking-empty">
			No thinking times in this match yet: bots do not think, and the runner records the time of
			model moves from the next build on.
		</p>
	{:else}
		<div class="scroll">
			<svg
				viewBox="0 0 {width} {H + 20}"
				{width}
				height={H + 20}
				role="img"
				aria-label="Thinking time per move"
			>
				{#each [0, top / 2, top] as tick (tick)}
					<line class="grid" x1="36" x2={width} y1={y(tick)} y2={y(tick)} />
					<text class="tick" x="32" y={y(tick) + 3} text-anchor="end">{seconds(tick)}</text>
				{/each}
				{#each data.moves as move, i (move.seq)}
					{#if move.latency_ms !== null}
						<rect
							class:slow={slow.has(move.seq)}
							x={40 + i * (BAR + 3)}
							y={y(move.latency_ms)}
							width={BAR}
							height={H - y(move.latency_ms)}
							rx="2"
							fill={colour(move.player)}
							role="button"
							tabindex="0"
							aria-label="{names[move.player] ?? move.player}, round {move.round}: {seconds(
								move.latency_ms
							)}"
							onclick={() => onjump?.(move.seq)}
							onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onjump?.(move.seq)}
						>
							<title
								>{names[move.player] ?? move.player}, round {move.round}: {seconds(
									move.latency_ms
								)}{move.tokens_out !== null
									? ` · ${move.tokens_in ?? '?'} in / ${move.tokens_out} out tokens`
									: ''}</title
							>
						</rect>
					{/if}
				{/each}
			</svg>
		</div>
	{/if}
</figure>

<style>
	.scroll {
		overflow-x: auto;
		scrollbar-width: thin;
	}

	svg {
		display: block;
	}

	.grid {
		stroke: var(--border);
	}

	.tick {
		font-size: 10px;
		fill: var(--muted);
	}

	rect {
		cursor: pointer;
	}

	rect.slow {
		stroke: var(--accent-2);
		stroke-width: 2;
	}

	rect:hover,
	rect:focus-visible {
		stroke: var(--text);
		stroke-width: 1.5;
		outline: none;
	}

	.empty {
		margin: 0;
		font-size: 0.85rem;
		color: var(--muted);
	}
</style>
