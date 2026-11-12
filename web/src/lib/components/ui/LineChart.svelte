<script lang="ts">
	import type { Identity } from '#lib/players.js';
	import PlayerMark from './PlayerMark.svelte';

	/**
	 * Lines over rounds, one per player in its slot colour and dash, labelled at their ends
	 * (no legend to look up), with at most four gridlines and vertical markers for key
	 * moments. SVG only, so it renders on the server. The full chart kit follows in step 3.
	 */
	let {
		x,
		lines,
		markers = [],
		label,
		unit = ''
	}: {
		x: number[];
		lines: { key: string; name: string; who: Identity; values: number[] }[];
		markers?: { at: number; kind: 'war' | 'betrayal' | 'conquest'; text: string }[];
		label: string;
		unit?: string;
	} = $props();

	// Drawn at its real width, so text and lines keep their size on a phone and on a wide screen.
	let width = $state(640);
	const W = $derived(Math.max(280, Math.round(width)));
	const H = $derived(W < 500 ? 200 : 240);
	const PAD = $derived({ top: 12, right: W < 500 ? 100 : 150, bottom: 26, left: 38 });
	const inner = $derived({ w: W - PAD.left - PAD.right, h: H - PAD.top - PAD.bottom });

	const max = $derived(Math.max(1, ...lines.flatMap((l) => l.values)));
	const top = $derived(niceTop(max));
	const ticks = $derived([0, 1, 2, 3].map((i) => (top * i) / 3));
	const first = $derived(x[0] ?? 0);
	const last = $derived(x.at(-1) ?? 1);
	const px = (v: number) => PAD.left + ((v - first) / Math.max(1, last - first)) * inner.w;
	const py = (v: number) => PAD.top + inner.h - (v / top) * inner.h;
	const path = (values: number[]) =>
		values.map((v, i) => `${i ? 'L' : 'M'}${px(x[i]).toFixed(1)},${py(v).toFixed(1)}`).join('');

	/** End labels, pushed apart so two close lines do not overlap. */
	const ends = $derived.by(() => {
		const placed = lines
			.map((l) => ({ ...l, y: py(l.values.at(-1) ?? 0), v: l.values.at(-1) ?? 0 }))
			.sort((a, b) => a.y - b.y);
		for (let i = 1; i < placed.length; i++)
			if (placed[i].y - placed[i - 1].y < 18) placed[i].y = placed[i - 1].y + 18;
		return placed;
	});

	function niceTop(v: number): number {
		const step = 10 ** Math.floor(Math.log10(v));
		for (const m of [1, 2, 2.5, 5, 10]) if (m * step >= v) return m * step;
		return 10 * step;
	}
	const COLOURS = { war: 'var(--danger)', betrayal: 'var(--danger)', conquest: 'var(--brand)' };
</script>

<div class="frame" bind:clientWidth={width}>
	<svg
		class="chart"
		width={W}
		height={H}
		viewBox="0 0 {W} {H}"
		role="img"
		aria-label={label}
		data-testid="line-chart"
	>
		{#each ticks as t (t)}
			<line class="grid" x1={PAD.left} x2={PAD.left + inner.w} y1={py(t)} y2={py(t)} />
			<text class="axis" x={PAD.left - 6} y={py(t) + 4} text-anchor="end"
				>{Math.round(t)}{unit}</text
			>
		{/each}
		{#each [first, Math.round((first + last) / 2), last] as r (r)}
			<text class="axis" x={px(r)} y={H - 6} text-anchor="middle">{r}</text>
		{/each}
		{#each markers as m, i (i)}
			<line
				class="marker"
				class:dashed={m.kind === 'conquest'}
				x1={px(m.at)}
				x2={px(m.at)}
				y1={PAD.top}
				y2={PAD.top + inner.h}
				stroke={COLOURS[m.kind]}
				data-testid="chart-marker"
				data-kind={m.kind}><title>Round {m.at}: {m.text}</title></line
			>
		{/each}
		{#each lines as l (l.key)}
			<path
				class="line"
				d={path(l.values)}
				stroke={l.who.colour}
				stroke-dasharray={l.who.dash}
				data-testid="chart-line"
				data-key={l.key}><title>{l.name}</title></path
			>
		{/each}
		{#each ends as e (e.key)}
			<foreignObject x={PAD.left + inner.w + 6} y={e.y - 9} width={PAD.right - 6} height="18">
				<span class="end" style="--who: {e.who.colour}"
					><PlayerMark who={e.who} size={11} /><b class="num">{e.v}</b><span>{e.name}</span></span
				>
			</foreignObject>
		{/each}
	</svg>
</div>

<style>
	.frame {
		width: 100%;
		min-width: 0;
	}

	.chart {
		display: block;
		overflow: visible;
	}
	.grid {
		stroke: var(--line);
		stroke-width: 1;
	}
	.axis {
		fill: var(--faint);
		font: 500 12px var(--font-mono);
	}
	.line {
		fill: none;
		stroke-width: 2.5;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.marker {
		stroke-width: 1.2;
		opacity: 0.75;
	}
	.marker.dashed {
		stroke-dasharray: 3 3;
	}
	.end {
		display: flex;
		align-items: center;
		gap: 4px;
		font: 600 12.5px/18px var(--font);
		color: var(--who);
		white-space: nowrap;
		overflow: hidden;
	}
	.end span {
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.end b {
		color: var(--text);
	}
</style>
