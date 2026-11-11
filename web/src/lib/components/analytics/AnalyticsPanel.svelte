<script lang="ts">
	import { slowMoves, upTo, type LiarsAnalytics } from '#lib/analytics/liars.js';
	import { pct, seconds } from '#lib/analytics/chart.js';
	import type { View } from '#lib/viewer.js';
	import CardsLeft from './CardsLeft.svelte';
	import MoveStrip from './MoveStrip.svelte';
	import PlayerBars from './PlayerBars.svelte';
	import RevolverRisk from './RevolverRisk.svelte';
	import RoundHeatmap from './RoundHeatmap.svelte';
	import ResponseBars from './ResponseBars.svelte';

	/**
	 * The Analytics tab: the arena's numbers about the match (GET /matches/{id}/analytics,
	 * docs/METRICS.md) as charts. In a replay they stop at the step on screen; live they are
	 * fetched again as turns come in (`version` changes). Clicking a move jumps to it.
	 */
	let {
		id,
		view,
		lastSeq = null,
		version = 0,
		names,
		colours,
		onjump
	}: {
		id: string;
		view: View;
		/** The newest event on screen; null for all of them. */
		lastSeq?: number | null;
		/** Anything that changes when new turns arrive, so a live match refetches. */
		version?: number;
		names: Record<string, string>;
		colours: Record<string, string>;
		onjump?: (seq: number) => void;
	} = $props();

	let load = $state<
		| { state: 'loading' }
		| { state: 'ok'; data: LiarsAnalytics }
		| { state: 'none' }
		| { state: 'error' }
	>({ state: 'loading' });

	$effect(() => {
		void version;
		const query = view === 'spoiler-free' ? '?view=spoiler-free' : '';
		const controller = new AbortController();
		const timer = setTimeout(() => {
			fetch(`/matches/${encodeURIComponent(id)}/analytics${query}`, { signal: controller.signal })
				.then(async (response) => {
					if (response.status === 404) load = { state: 'none' };
					else if (!response.ok) load = { state: 'error' };
					else load = { state: 'ok', data: await response.json() };
				})
				.catch((error) => {
					if (error?.name !== 'AbortError') load = { state: 'error' };
				});
		}, 150);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});

	const shown = $derived(load.state === 'ok' ? upTo(load.data, lastSeq) : null);
	const slow = $derived(shown ? slowMoves(shown.moves) : new Set<number>());
	const sum = (pick: (t: LiarsAnalytics['totals'][string]) => number) =>
		shown ? Object.values(shown.totals).reduce((a, t) => a + pick(t), 0) : 0;
	const allLies = $derived(sum((t) => t.lies));
	const allKnown = $derived(sum((t) => t.plays_known));
	const caught = $derived(sum((t) => t.lies_called));
	const response = $derived(
		shown
			? (() => {
					const times = shown.moves.map((m) => m.latency_ms).filter((v): v is number => v !== null);
					return times.length ? times.reduce((a, b) => a + b, 0) / times.length : null;
				})()
			: null
	);
</script>

<section class="analytics" aria-label="Analytics" data-testid="analytics">
	{#if load.state === 'loading'}
		<p class="status">Loading the numbers…</p>
	{:else if load.state === 'none'}
		<p class="status" data-testid="analytics-none">
			Analytics for this game are coming; Liar's Deck has them first.
		</p>
	{:else if load.state === 'error'}
		<p class="status problem" role="status">The analytics did not load.</p>
	{:else if shown}
		<ul class="kpis" aria-label="Key numbers">
			<li><b data-testid="kpi-moves">{shown.moves.length}</b><span>moves</span></li>
			{#if shown.spoilers}
				<li>
					<b>{pct(allKnown ? allLies / allKnown : null)}</b><span>of the plays were lies</span>
				</li>
			{:else}
				<li><b>{allLies}</b><span>lies revealed by a call</span></li>
			{/if}
			<li><b>{caught} / {allLies}</b><span>lies caught</span></li>
			<li>
				<b>{shown.pulls.filter((p) => p.live).length} / {shown.pulls.length}</b><span
					>pulls fired</span
				>
			</li>
			<li><b>{seconds(response)}</b><span>mean response time</span></li>
		</ul>

		<MoveStrip data={shown} {names} {slow} {onjump} />
		<div class="grid">
			<PlayerBars data={shown} {names} />
			<RoundHeatmap data={shown} {names} {onjump} />
			<RevolverRisk data={shown} {names} {onjump} />
			<CardsLeft data={shown} {names} {colours} />
		</div>
		<ResponseBars data={shown} {names} {colours} {slow} {onjump} />
		<p class="foot">
			{#if view === 'spoiler-free'}Spoiler-free: only what every player saw counts here.{:else}Spectator
				view: hidden cards and the revolver loading are counted.{/if}
			Definitions: <code>docs/METRICS.md</code>.
		</p>
	{/if}
</section>

<style>
	.analytics {
		display: grid;
		gap: 0.9rem;
		min-width: 0;
		padding: 0.9rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.status {
		margin: 0;
		color: var(--muted);
	}

	.problem {
		color: var(--danger);
	}

	.kpis {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(7.5rem, 1fr));
		gap: 0.5rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.kpis li {
		display: grid;
		gap: 0.1rem;
		padding: 0.5rem 0.7rem;
		border-radius: 10px;
		background: var(--surface-raised);
	}

	.kpis b {
		font-size: 1.25rem;
		font-variant-numeric: tabular-nums;
		color: var(--accent);
	}

	.kpis span {
		font-size: 0.75rem;
		color: var(--muted);
	}

	.grid {
		display: grid;
		gap: 0.9rem;
	}

	@media (min-width: 52rem) {
		.grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.foot {
		margin: 0;
		font-size: 0.75rem;
		color: var(--muted);
	}

	/* Shared by every chart of the tab. */
	.analytics :global(.chart) {
		display: grid;
		gap: 0.5rem;
		margin: 0;
		min-width: 0;
		padding: 0.75rem;
		border-radius: 10px;
		background: color-mix(in srgb, var(--surface-raised) 55%, transparent);
		border: 1px solid var(--border);
	}

	.analytics :global(figcaption) {
		font-size: 0.875rem;
		font-weight: 650;
	}

	.analytics :global(figcaption small) {
		font-weight: 400;
		color: var(--muted);
	}

	.analytics :global(.legend) {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 0.8rem;
		margin: 0;
		padding: 0;
		list-style: none;
		font-size: 0.75rem;
		color: var(--muted);
	}

	.analytics :global(.legend i) {
		display: inline-block;
		width: 0.7rem;
		height: 0.7rem;
		margin-right: 0.3rem;
		border-radius: 3px;
		vertical-align: -0.05rem;
	}

	.analytics :global(.note) {
		margin: 0;
		font-size: 0.75rem;
		color: var(--muted);
	}
</style>
