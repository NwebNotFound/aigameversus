<script lang="ts">
	import { leadAnswer, markers, tiles, verdict, type CivAnalytics } from '#lib/analytics/civ.js';
	import { identities } from '#lib/players.js';
	import Card from '#lib/components/ui/Card.svelte';
	import DataTable from '#lib/components/ui/DataTable.svelte';
	import LineChart from '#lib/components/ui/LineChart.svelte';
	import PlayerName from '#lib/components/ui/PlayerName.svelte';
	import StatTile from '#lib/components/ui/StatTile.svelte';

	/**
	 * The Throne of Tokens Report (design review section 5, cards 0, 1 and 12): the verdict
	 * with six numbers, who was ahead and when it turned, and what each seat cost and
	 * bought. Spectator view only for the per-round parts; the spoiler-free view gets the
	 * verdict, the public counts and a note on what is hidden. The other cards follow.
	 */
	let {
		data,
		names,
		costs = null
	}: {
		data: CivAnalytics;
		names: Record<string, string>;
		/** Micro-euros per seat (`GET /matches/{id}/cost`), or null when unknown. */
		costs?: Record<string, number> | null;
	} = $props();

	const name = (seat: string) => names[seat] ?? data.meta.seats?.[seat] ?? seat;
	const who = $derived(identities(data.nations));
	const answer = $derived(verdict(data, name));
	const t = $derived(tiles(data));
	const share = (r: { n: number; of: number } | null) =>
		r && r.of ? `${Math.round((r.n / r.of) * 100)} %` : '–';
	const score = (seat: string) => data.series?.nations[seat]?.score.at(-1) ?? null;
	const ranked = $derived(
		[...(data.victory?.standings ?? [])].sort((a, b) => a.rank - b.rank).map((s) => s.player)
	);
	const order = $derived(ranked.length ? ranked : data.nations);
	const seconds = (ms: number | null) => (ms === null ? '–' : `${(ms / 1000).toFixed(1)} s`);
	const thousands = (n: number | null) =>
		n === null ? '–' : n >= 10000 ? `${(n / 1000).toFixed(0)}k` : n.toLocaleString('en');
	const euro = (micro: number | null | undefined) =>
		micro === null || micro === undefined ? '–' : `${(micro / 1e6).toFixed(4)} €`;
	const perPoint = (seat: string) => {
		const s = score(seat);
		const c = costs?.[seat];
		return s && c !== undefined && c !== null ? euro(c / s) : '–';
	};
</script>

<div class="report" data-testid="civ-report">
	<section class="verdict" data-testid="civ-verdict">
		<p class="caption">Verdict</p>
		<h2>{answer ?? 'The match is still running.'}</h2>
		<div class="tiles">
			<StatTile
				value={t.battles ?? '–'}
				label={t.nationBattles !== null
					? `battles, ${t.nationBattles} between nations`
					: 'battles (spectator view)'}
				testid="tile-battles"
			/>
			<StatTile value={t.treaties} label="treaties signed" tone={t.treaties ? 'ok' : 'plain'} />
			<StatTile
				value={t.wars}
				label={t.betrayals ? `wars declared, ${t.betrayals} breaking a treaty` : 'wars declared'}
				tone={t.betrayals ? 'danger' : 'plain'}
				testid="tile-wars"
			/>
			<StatTile
				value={t.dropped ? share(t.dropped) : '–'}
				label={t.dropped
					? `orders dropped (${t.dropped.n} of ${t.dropped.of})`
					: 'orders dropped (spectator view)'}
				tone={t.dropped && t.dropped.n ? 'warn' : 'plain'}
				testid="tile-dropped"
			/>
			<StatTile
				value={t.cutoffs ? share(t.cutoffs) : '–'}
				label={t.cutoffs
					? `answers cut off at the limit (${t.cutoffs.n} of ${t.cutoffs.of})`
					: 'answers cut off (spectator view)'}
				tone={t.cutoffs && t.cutoffs.n ? 'warn' : 'plain'}
			/>
			<StatTile
				value={costs ? euro(Object.values(costs).reduce((a, b) => a + b, 0)) : '–'}
				label="model cost of the match"
			/>
		</div>
	</section>

	{#if data.series}
		<Card
			question="Who was ahead, and when did it turn?"
			answer={leadAnswer(data, name)}
			testid="civ-score"
		>
			<LineChart
				label="Score per nation and round"
				x={data.series.rounds}
				lines={data.nations.map((seat) => ({
					key: seat,
					name: name(seat),
					who: who[seat],
					values: data.series?.nations[seat]?.score ?? []
				}))}
				markers={markers(data, name).map((m) => ({ at: m.round, kind: m.kind, text: m.text }))}
			/>
			<p class="legend">
				<span><i class="war"></i>war declared</span>
				<span><i class="conquest"></i>city changed hands</span>
			</p>
		</Card>
	{/if}

	{#if data.decisions}
		<Card
			question="What did each seat cost, and what did it buy?"
			answer="Score at the end against time, tokens and answers the engine had to deal with."
			testid="civ-seats"
		>
			<DataTable label="Cost and answers per seat">
				<thead>
					<tr>
						<th>Seat</th>
						<th class="num">Score</th>
						<th class="num">Mean response</th>
						<th class="num">Tokens in</th>
						<th class="num">Tokens out</th>
						<th class="num">Cut off</th>
						<th class="num">Refused</th>
						<th class="num">Bot moves</th>
						<th class="num">Cost</th>
						<th class="num">Per point</th>
					</tr>
				</thead>
				<tbody>
					{#each order as seat (seat)}
						{@const d = data.decisions[seat]}
						<tr data-seat={seat}>
							<td><PlayerName who={who[seat]} name={name(seat)} /></td>
							<td class="num">{score(seat) ?? '–'}</td>
							<td class="num">{seconds(d?.response_ms_mean ?? null)}</td>
							<td class="num">{thousands(d?.tokens_in ?? null)}</td>
							<td class="num">{thousands(d?.tokens_out ?? null)}</td>
							<td class="num" class:warn={(d?.cutoffs ?? 0) > 0}
								>{d ? `${d.cutoffs} / ${d.model_moves}` : '–'}</td
							>
							<td class="num">{d?.rejected ?? '–'}</td>
							<td class="num" class:warn={(d?.fallbacks ?? 0) > 0}>{d?.fallbacks ?? '–'}</td>
							<td class="num">{euro(costs?.[seat])}</td>
							<td class="num">{perPoint(seat)}</td>
						</tr>
					{/each}
				</tbody>
			</DataTable>
			<p class="note">
				Response time includes the network and the provider's queue. Bot moves are moves the engine
				played for the seat.
			</p>
		</Card>
	{/if}

	{#if !data.spoilers}
		<Card
			question="What is hidden here?"
			answer="Each nation's economy, armies, battles, orders and thoughts. Switch to the Spectator view to see them."
			testid="civ-hidden"
		/>
	{/if}
</div>

<style>
	.report {
		display: grid;
		gap: 12px;
		min-width: 0;
	}

	.verdict {
		display: grid;
		gap: 0.5rem;
		padding: 14px;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--line);
	}

	.verdict .caption {
		margin: 0;
	}

	.verdict h2 {
		margin: 0;
		font: var(--t-display);
	}

	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(8.75rem, 1fr));
		gap: 8px;
		margin-top: 0.25rem;
	}

	.legend {
		display: flex;
		gap: 1rem;
		margin: 0.5rem 0 0;
		font: var(--t-small);
		color: var(--muted);
	}

	.legend span {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}

	.legend i {
		width: 1px;
		height: 0.8rem;
		border-left: 2px solid var(--danger);
	}

	.legend i.conquest {
		border-left: 2px dashed var(--brand);
	}

	td.warn {
		color: var(--brand);
	}

	.note {
		margin: 0.5rem 0 0;
		font: var(--t-small);
		color: var(--faint);
	}
</style>
