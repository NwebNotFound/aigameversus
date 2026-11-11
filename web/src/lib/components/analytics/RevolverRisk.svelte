<script lang="ts">
	import type { LiarsAnalytics } from '#lib/analytics/liars.js';
	import { pct } from '#lib/analytics/chart.js';

	/**
	 * Every trigger pull of the match, per player: survived (ring) or fired (filled red), and
	 * the chance it would fire at that moment (public: live chambers over chambers left).
	 */
	let {
		data,
		names,
		onjump
	}: { data: LiarsAnalytics; names: Record<string, string>; onjump?: (seq: number) => void } =
		$props();
</script>

<figure class="chart" data-testid="chart-revolver">
	<figcaption>
		Trigger pulls <small>with the chance each one fired</small>
	</figcaption>
	{#if data.pulls.length === 0}
		<p class="empty">Nobody has pulled the trigger yet.</p>
	{:else}
		<ul class="rows">
			{#each data.players as player (player)}
				{@const mine = data.pulls.filter((p) => p.player === player)}
				<li>
					<span class="who">{names[player] ?? player}</span>
					<span class="pulls">
						{#each mine as pull (pull.seq)}
							<button
								class="pull"
								class:live={pull.live}
								onclick={() => onjump?.(pull.seq)}
								title="Round {pull.round}, pull {pull.pull}: {pull.live
									? 'fired'
									: 'survived'}{pull.risk !== null ? ` (chance ${pct(pull.risk)})` : ''}"
								data-testid="pull"
							>
								{#if pull.risk !== null}<span
										class="risk"
										style="height: {Math.round(pull.risk * 100)}%"
									></span>{/if}
								<span class="mark"></span>
							</button>
						{/each}
						{#if mine.length === 0}<small>no pull</small>{/if}
					</span>
				</li>
			{/each}
		</ul>
	{/if}
</figure>

<style>
	.rows {
		display: grid;
		gap: 0.4rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	li {
		display: grid;
		grid-template-columns: minmax(5rem, 9rem) 1fr;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.85rem;
	}

	.who {
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.pulls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.pulls small {
		color: var(--muted);
	}

	.pull {
		position: relative;
		display: grid;
		place-items: center;
		width: 1.6rem;
		height: 1.6rem;
		padding: 0;
		border-radius: 6px;
		border: 1px solid var(--border);
		background: var(--surface-raised);
		cursor: pointer;
		overflow: hidden;
	}

	.risk {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		background: color-mix(in srgb, var(--danger) 28%, transparent);
	}

	.mark {
		position: relative;
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 50%;
		border: 2px solid var(--text);
	}

	.pull.live .mark {
		border-color: var(--danger);
		background: var(--danger);
	}

	.empty {
		margin: 0;
		font-size: 0.85rem;
		color: var(--muted);
	}
</style>
