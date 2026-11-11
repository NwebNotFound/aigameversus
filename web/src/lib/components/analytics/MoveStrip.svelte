<script lang="ts">
	import type { LiarsAnalytics, LiarsMove } from '#lib/analytics/liars.js';

	/**
	 * Every move of the match in order, one cell each, a row per player: honest plays green,
	 * lies red, plays whose cards nobody saw grey, calls as a brass diamond. A ring marks a
	 * play that was called; a dot a slow move. Clicking a cell jumps the replay to it.
	 */
	let {
		data,
		names,
		slow,
		onjump
	}: {
		data: LiarsAnalytics;
		names: Record<string, string>;
		slow: Set<number>;
		onjump?: (seq: number) => void;
	} = $props();

	const CELL = 14;
	const GAP = 3;
	/** The name column fits the longest name (about 7 px a letter at 12 px), within bounds. */
	const LABEL = $derived(
		Math.min(
			220,
			Math.max(80, 16 + 7 * Math.max(...data.players.map((p) => (names[p] ?? p).length)))
		)
	);
	const columns = $derived(Math.max(data.moves.length, 1));
	const width = $derived(LABEL + columns * (CELL + GAP));
	const rows = $derived(data.players.length);

	function state(move: LiarsMove): string {
		if (move.kind === 'call')
			return move.correct === true ? 'call-right' : move.correct === false ? 'call-wrong' : 'call';
		return move.honest === true ? 'honest' : move.honest === false ? 'lie' : 'unknown';
	}

	function title(move: LiarsMove): string {
		const who = names[move.player] ?? move.player;
		if (move.kind === 'call') {
			const target = names[move.target ?? ''] ?? move.target;
			const verdict =
				move.correct === true ? 'right' : move.correct === false ? 'wrong' : 'not judged';
			return `Round ${move.round}: ${who} calls ${target} a liar (${verdict})`;
		}
		const truth =
			move.honest === true ? 'honest' : move.honest === false ? 'a lie' : 'cards not shown';
		const extra = [
			move.called ? 'called' : null,
			move.fallback ? 'random fallback' : null,
			move.latency_ms !== null ? `${(move.latency_ms / 1000).toFixed(1)} s` : null
		].filter(Boolean);
		return `Round ${move.round}: ${who} plays ${move.cards} (${truth})${extra.length ? ', ' + extra.join(', ') : ''}`;
	}

	/** Where a round starts, for the separators. */
	const roundStarts = $derived(
		data.moves.flatMap((m, i) => (i > 0 && data.moves[i - 1].round !== m.round ? [i] : []))
	);
</script>

<figure class="chart" data-testid="chart-moves">
	<figcaption>
		Every move <small>by player, in order · ring = called · dot = slow</small>
	</figcaption>
	<div class="scroll">
		<svg
			viewBox="0 0 {width} {rows * (CELL + GAP) + 18}"
			{width}
			height={rows * (CELL + GAP) + 18}
			role="img"
			aria-label="Moves of the match by player: honest plays, lies and calls"
		>
			{#each roundStarts as i (i)}
				<line
					class="sep"
					x1={LABEL + i * (CELL + GAP) - GAP / 2}
					x2={LABEL + i * (CELL + GAP) - GAP / 2}
					y1="0"
					y2={rows * (CELL + GAP)}
				/>
			{/each}
			{#each data.players as player, row (player)}
				<text class="label" x={LABEL - 8} y={row * (CELL + GAP) + CELL - 3} text-anchor="end"
					>{names[player] ?? player}</text
				>
			{/each}
			{#each data.moves as move, i (move.seq)}
				{@const row = data.players.indexOf(move.player)}
				{@const x = LABEL + i * (CELL + GAP)}
				{@const y = row * (CELL + GAP)}
				<g
					class="cell {state(move)}"
					role="button"
					tabindex="0"
					aria-label={title(move)}
					data-seq={move.seq}
					data-state={state(move)}
					onclick={() => onjump?.(move.seq)}
					onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && onjump?.(move.seq)}
				>
					<title>{title(move)}</title>
					{#if move.kind === 'call'}
						<rect
							x={x + 2}
							y={y + 2}
							width={CELL - 4}
							height={CELL - 4}
							transform="rotate(45 {x + CELL / 2} {y + CELL / 2})"
							rx="1.5"
						/>
					{:else}
						<rect {x} {y} width={CELL} height={CELL} rx="3" />
						{#if move.called}<rect
								class="ring"
								x={x - 1.5}
								y={y - 1.5}
								width={CELL + 3}
								height={CELL + 3}
								rx="4"
							/>{/if}
					{/if}
					{#if slow.has(move.seq)}<circle class="slow" cx={x + CELL / 2} cy={y - 3} r="2" />{/if}
					{#if move.fallback}<text class="fb" x={x + CELL / 2} y={y + CELL - 3} text-anchor="middle"
							>r</text
						>{/if}
				</g>
			{/each}
			{#each data.rounds as round, i (round.round)}
				{@const start = data.moves.findIndex((m) => m.round === round.round)}
				{#if start >= 0}
					<text class="round" x={LABEL + start * (CELL + GAP)} y={rows * (CELL + GAP) + 13}
						>R{round.round}{i === 0 ? ` · ${round.table_card}` : ''}</text
					>
				{/if}
			{/each}
		</svg>
	</div>
	<ul class="legend">
		<li><i class="honest"></i>honest</li>
		<li><i class="lie"></i>lie</li>
		<li><i class="unknown"></i>cards not shown</li>
		<li><i class="call-right"></i>right call</li>
		<li><i class="call-wrong"></i>wrong call</li>
		<li><b>r</b> random fallback</li>
	</ul>
</figure>

<style>
	.scroll {
		overflow-x: auto;
		scrollbar-width: thin;
	}

	svg {
		display: block;
	}

	.label {
		font-size: 12px;
		font-weight: 600;
		fill: var(--text);
	}

	.round {
		font-size: 10px;
		fill: var(--muted);
	}

	.sep {
		stroke: var(--border);
		stroke-dasharray: 2 2;
	}

	.cell {
		cursor: pointer;
		outline: none;
	}

	.cell rect {
		stroke: none;
	}

	.cell:hover rect:first-of-type,
	.cell:focus-visible rect:first-of-type {
		stroke: var(--text);
		stroke-width: 1.5;
	}

	.honest rect,
	i.honest {
		fill: var(--ok);
		background: var(--ok);
	}
	.lie rect,
	i.lie {
		fill: var(--danger);
		background: var(--danger);
	}
	.unknown rect,
	i.unknown {
		fill: #5a5468;
		background: #5a5468;
	}
	.call rect,
	.call-right rect,
	i.call-right {
		fill: var(--accent);
		background: var(--accent);
	}
	.call-wrong rect,
	i.call-wrong {
		fill: color-mix(in srgb, var(--accent) 35%, #3a3346);
		background: color-mix(in srgb, var(--accent) 35%, #3a3346);
	}

	.cell rect.ring {
		fill: none;
		stroke: var(--text);
		stroke-width: 1.2;
	}

	.slow {
		fill: var(--accent-2);
	}

	.fb {
		font-size: 9px;
		font-weight: 700;
		fill: #0d0c12;
		pointer-events: none;
	}
</style>
