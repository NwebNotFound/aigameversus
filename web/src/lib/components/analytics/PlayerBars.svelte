<script lang="ts">
	import type { LiarsAnalytics } from '#lib/analytics/liars.js';
	import { pct } from '#lib/analytics/chart.js';

	/**
	 * Per player: honest plays against lies (and plays nobody saw), and chosen calls that
	 * were right against wrong, as stacked bars on one common scale.
	 */
	let { data, names }: { data: LiarsAnalytics; names: Record<string, string> } = $props();

	/** "3 of 12": how many a rate rests on, so a small sample reads as one. */
	const rateTitle = (r: { n: number; of: number } | null) =>
		r ? `${r.n} of ${r.of}` : 'needs the hidden cards';

	const most = $derived(
		Math.max(
			1,
			...data.players.map((p) => {
				const t = data.totals[p];
				return Math.max(t.plays, t.calls);
			})
		)
	);
	const w = (n: number) => `${(n / most) * 100}%`;
</script>

<figure class="chart" data-testid="chart-players">
	<figcaption>Honesty and calls <small>per player</small></figcaption>
	<table>
		<thead>
			<tr>
				<th scope="col">Player</th>
				<th scope="col">Plays: honest · lie · not shown</th>
				<th scope="col">Calls: right · wrong</th>
				<th scope="col" class="num">Lie rate</th>
				<th scope="col" class="num">Call accuracy</th>
			</tr>
		</thead>
		<tbody>
			{#each data.players as player (player)}
				{@const t = data.totals[player]}
				<tr data-player={player}>
					<th scope="row">{names[player] ?? player}</th>
					<td>
						<span
							class="bar"
							title="{t.honest} honest, {t.lies} lies, {t.plays - t.plays_known} not shown"
						>
							<i class="honest" style="width: {w(t.honest)}"></i><i
								class="lie"
								style="width: {w(t.lies)}"
							></i><i class="unknown" style="width: {w(t.plays - t.plays_known)}"></i>
						</span>
						<small
							>{t.honest} · {t.lies}{t.plays > t.plays_known
								? ` · ${t.plays - t.plays_known}`
								: ''}</small
						>
					</td>
					<td>
						<span class="bar" title="{t.calls_correct} right, {t.calls_wrong} wrong">
							<i class="right" style="width: {w(t.calls_correct)}"></i><i
								class="wrong"
								style="width: {w(t.calls_wrong)}"
							></i>
						</span>
						<small>{t.calls_correct} · {t.calls_wrong}</small>
					</td>
					<td class="num" data-testid="lie-rate" title={rateTitle(t.lie_rate)}
						>{pct(t.lie_rate?.value)}</td
					>
					<td class="num" title={rateTitle(t.call_accuracy)}>{pct(t.call_accuracy?.value)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
	{#if !data.spoilers}
		<p class="note">
			Spoiler-free: a lie counts only once its cards were turned over, so lie rates need the
			spectator view.
		</p>
	{/if}
	<p class="note">Moves the engine played for a model (random fallbacks) are not counted here.</p>
</figure>

<style>
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.85rem;
	}

	th,
	td {
		padding: 0.35rem 0.4rem;
		text-align: left;
		border-top: 1px solid var(--border);
		vertical-align: middle;
	}

	thead th {
		border-top: 0;
		font-size: 0.75rem;
		font-weight: 600;
		color: var(--muted);
	}

	tbody th {
		font-weight: 600;
		white-space: nowrap;
	}

	.num {
		text-align: right;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	td small {
		display: block;
		font-size: 0.75rem;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}

	.bar {
		display: flex;
		height: 0.6rem;
		min-width: 4rem;
		border-radius: 999px;
		background: var(--surface-raised);
		overflow: hidden;
	}

	.bar i {
		display: block;
		height: 100%;
	}

	.honest {
		background: var(--ok);
	}
	.lie {
		background: var(--danger);
	}
	.unknown {
		background: #5a5468;
	}
	.right {
		background: var(--accent);
	}
	.wrong {
		background: color-mix(in srgb, var(--accent) 35%, #3a3346);
	}

	@media (max-width: 30rem) {
		thead th:nth-child(5),
		tbody td:nth-child(5) {
			display: none;
		}
	}
</style>
