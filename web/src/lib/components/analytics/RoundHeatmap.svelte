<script lang="ts">
	import type { LiarsAnalytics } from '#lib/analytics/liars.js';

	/**
	 * Player by round: each cell's colour is the share of lies among that player's known
	 * plays of the round (green honest to red lying), its number the plays; empty when the
	 * player sat the round out or made no play. Clicking a cell jumps to the round.
	 */
	let {
		data,
		names,
		onjump
	}: { data: LiarsAnalytics; names: Record<string, string>; onjump?: (seq: number) => void } =
		$props();

	function cell(round: number, player: string) {
		const c = data.by_round.find((r) => r.round === round)?.players[player];
		if (!c) return null;
		const plays = c.honest + c.lies + c.unknown;
		const known = c.honest + c.lies;
		return { plays, calls: c.calls, lieShare: known ? c.lies / known : null, unknown: c.unknown };
	}

	/** Lie share 0..1 as a colour from honest green to lying red; grey when unknown. */
	const colour = (share: number | null) =>
		share === null
			? '#4a4558'
			: `color-mix(in oklch, var(--danger) ${Math.round(share * 100)}%, var(--ok))`;

	const startOf = (round: number) => data.moves.find((m) => m.round === round)?.seq;
</script>

<figure class="chart" data-testid="chart-heatmap">
	<figcaption>Rounds <small>lie share of each player's plays · number = plays</small></figcaption>
	<div class="scroll">
		<table>
			<thead>
				<tr>
					<th></th>
					{#each data.rounds as round (round.round)}
						<th scope="col">
							<button
								class="round"
								onclick={() => {
									const seq = startOf(round.round);
									if (seq !== undefined) onjump?.(seq);
								}}
								title="Round {round.round}: table card {round.table_card}">R{round.round}</button
							>
						</th>
					{/each}
				</tr>
			</thead>
			<tbody>
				{#each data.players as player (player)}
					<tr>
						<th scope="row">{names[player] ?? player}</th>
						{#each data.rounds as round (round.round)}
							{@const c = round.players.includes(player) ? cell(round.round, player) : null}
							<td>
								{#if c && (c.plays || c.calls)}
									<span
										class="heat"
										style="background: {c.plays ? colour(c.lieShare) : 'transparent'}"
										title="Round {round.round}: {c.plays} plays{c.lieShare !== null
											? `, ${Math.round(c.lieShare * 100)} % lies`
											: ''}{c.unknown ? `, ${c.unknown} not shown` : ''}{c.calls
											? `, ${c.calls} call`
											: ''}"
										data-testid="heat-cell"
									>
										{c.plays || ''}{#if c.calls}<b>◆</b>{/if}
									</span>
								{:else if !round.players.includes(player)}
									<span class="out" title="Out of the game">·</span>
								{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</figure>

<style>
	.scroll {
		overflow-x: auto;
		scrollbar-width: thin;
	}

	table {
		border-collapse: separate;
		border-spacing: 3px;
		font-size: 0.8rem;
	}

	th {
		font-weight: 600;
		text-align: right;
		padding-right: 0.4rem;
		white-space: nowrap;
	}

	thead th {
		text-align: center;
		padding: 0;
	}

	.round {
		font: inherit;
		font-size: 0.75rem;
		color: var(--muted);
		background: none;
		border: 0;
		cursor: pointer;
		padding: 0.1rem 0.2rem;
	}

	.round:hover {
		color: var(--text);
	}

	td {
		padding: 0;
	}

	.heat {
		display: grid;
		place-items: center;
		grid-auto-flow: column;
		gap: 0.1rem;
		width: 2rem;
		height: 1.6rem;
		border-radius: 5px;
		color: #0d0c12;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
	}

	.heat b {
		font-size: 0.75rem;
		color: #3a2400;
	}

	.out {
		display: grid;
		place-items: center;
		width: 2rem;
		height: 1.6rem;
		color: var(--border);
	}
</style>
