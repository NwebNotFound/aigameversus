<script lang="ts">
	import { roleName, isWolf } from '#lib/boards/werewolfCircle.js';
	import {
		claimsUpTo,
		mostSuspected,
		suspicion,
		type Accusation,
		type Claim
	} from '#lib/boards/werewolfIntel.js';
	import Avatar from '#lib/components/Avatar.svelte';

	/**
	 * Under the Werewolf circle: what the table said about itself up to the moment on
	 * screen. "Who claims what" lists each player's claimed roles with what became of them;
	 * "Who suspects whom" is a grid of accuser by target, shaded by accusing sentences, with a
	 * dot for votes. Both come from the match analytics; the claims and speech readings are
	 * heuristic (docs/METRICS.md), and the panel says so.
	 */
	let {
		seats,
		claims,
		accusations,
		lastSeq,
		spoilers,
		label,
		colours = {},
		alive = {}
	}: {
		seats: string[];
		claims: Claim[];
		accusations: Accusation[];
		lastSeq: number | null;
		spoilers: boolean;
		label: (seat: string) => string;
		colours?: Record<string, string>;
		alive?: Record<string, boolean>;
	} = $props();

	const claimed = $derived(claimsUpTo(claims, lastSeq));
	const grid = $derived(suspicion(accusations, lastSeq));
	const top = $derived(mostSuspected(accusations, lastSeq));
	const shade = (n: number) => (grid.max ? 0.15 + 0.85 * (n / grid.max) : 0);
	const initial = (seat: string) => label(seat).trim().charAt(0).toUpperCase() || '?';

	/** What became of a claim, in a few words, or null when nothing is known yet. */
	function fate(c: Claim): { text: string; tone: 'lie' | 'true' | 'note' } | null {
		if (c.disproved) return { text: `disproved: was ${roleName(c.true_role)}`, tone: 'lie' };
		if (c.lie === true) return { text: spoilers ? 'a lie' : 'a lie (revealed)', tone: 'lie' };
		if (c.lie === false && spoilers) return { text: 'true', tone: 'true' };
		if (c.counterclaimed_by.length)
			return {
				text: `counter-claimed by ${c.counterclaimed_by.map(label).join(', ')}`,
				tone: 'note'
			};
		if (c.changed_from) return { text: `changed from ${roleName(c.changed_from)}`, tone: 'note' };
		return null;
	}
</script>

<section class="intel" aria-label="What the table says" data-testid="werewolf-intel">
	<div class="card claims" data-testid="claims">
		<h3>Who claims what</h3>
		{#if claimed.size === 0}
			<p class="empty">No role claimed yet.</p>
		{:else}
			<ul>
				{#each seats.filter((s) => claimed.has(s)) as seat (seat)}
					<li class:dead={alive[seat] === false} data-seat={seat}>
						<Avatar
							name={label(seat)}
							colourKey={colours[seat] ?? seat}
							size={20}
							out={alive[seat] === false}
						/>
						<span class="who">{label(seat)}</span>
						<span class="roles">
							{#each claimed.get(seat) ?? [] as c (c.seq)}
								{@const f = fate(c)}
								<span
									class="claim"
									class:wolfish={isWolf(c.role)}
									data-testid="claim"
									data-role={c.role}
									>{roleName(c.role)}{#if f}<small class={f.tone} data-testid="claim-fate"
											>{f.text}</small
										>{/if}</span
								>
							{/each}
						</span>
					</li>
				{/each}
			</ul>
		{/if}
	</div>

	<div class="card matrix" data-testid="suspicion">
		<h3>
			Who suspects whom
			{#if top}<span class="top" data-testid="most-suspected"
					>most suspected: <b>{label(top)}</b></span
				>{/if}
		</h3>
		{#if grid.max === 0}
			<p class="empty">No accusations yet.</p>
		{:else}
			<div class="scroll">
				<table>
					<caption class="sr-only"
						>Rows accuse columns: shaded by sentences, a dot per vote.</caption
					>
					<thead>
						<tr>
							<th scope="col"><span class="sr-only">Accuser</span></th>
							{#each seats as target (target)}
								<th scope="col" title={label(target)} class:dead={alive[target] === false}>
									<span class="ini">{initial(target)}</span>
								</th>
							{/each}
						</tr>
					</thead>
					<tbody>
						{#each seats as by (by)}
							<tr class:dead={alive[by] === false}>
								<th scope="row" title={label(by)}>{label(by)}</th>
								{#each seats as target (target)}
									{@const cell = grid.cells.get(by)?.get(target)}
									<td
										class:self={by === target}
										data-testid={cell ? 'suspicion-cell' : undefined}
										data-by={by}
										data-target={target}
										title={cell
											? `${label(by)} on ${label(target)}: ${cell.speech} accusing ${cell.speech === 1 ? 'sentence' : 'sentences'}, ${cell.votes} ${cell.votes === 1 ? 'vote' : 'votes'}`
											: undefined}
									>
										{#if cell}
											<i style="opacity: {shade(cell.speech + cell.votes)}"></i>
											{#if cell.votes}<b class="vote" aria-hidden="true"
													>{cell.votes > 1 ? cell.votes : ''}</b
												>{/if}
										{/if}
									</td>
								{/each}
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</div>
	<p class="note">
		Claims and accusations are read from what players said, by simple rules: a guide, not proof.
	</p>
</section>

<style>
	.intel {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
		gap: 0.6rem;
		margin-top: 0.75rem;
	}

	.card {
		min-width: 0;
		padding: 0.65rem 0.75rem;
		border-radius: 12px;
		background: var(--surface);
		border: 1px solid var(--border);
	}

	h3 {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.6rem;
		margin: 0 0 0.5rem;
		font-size: 0.72rem;
		font-weight: 650;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--muted);
	}

	.top {
		letter-spacing: 0;
		text-transform: none;
		font-weight: 500;
	}

	.top b {
		color: #ffb347;
	}

	.empty {
		margin: 0;
		font-size: 0.85rem;
		color: var(--muted);
	}

	.claims ul {
		display: grid;
		gap: 0.35rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.claims li {
		display: grid;
		grid-template-columns: auto minmax(4rem, 7rem) 1fr;
		align-items: center;
		gap: 0.45rem;
		font-size: 0.82rem;
	}

	.claims li.dead .who {
		color: var(--muted);
		text-decoration: line-through;
		text-decoration-thickness: 1px;
	}

	.who {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.roles {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}

	.claim {
		display: inline-flex;
		align-items: baseline;
		gap: 0.3rem;
		padding: 0.05rem 0.5rem;
		border-radius: 999px;
		background: var(--surface-raised);
		border: 1px solid var(--border);
		color: var(--accent-2);
	}

	.claim small {
		font-size: 0.7rem;
		color: var(--muted);
	}

	.claim small.lie {
		color: var(--danger);
	}

	.claim small.true {
		color: var(--ok);
	}

	.scroll {
		overflow-x: auto;
	}

	table {
		border-collapse: collapse;
		font-size: 0.75rem;
	}

	th,
	td {
		padding: 0;
		text-align: center;
	}

	tbody th {
		max-width: 6rem;
		padding-right: 0.4rem;
		text-align: right;
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	tr.dead th,
	thead th.dead {
		color: var(--muted);
		opacity: 0.6;
	}

	.ini {
		display: inline-grid;
		place-items: center;
		width: 1.25rem;
		height: 1.25rem;
		font-weight: 650;
		color: var(--muted);
	}

	td {
		position: relative;
		width: 1.35rem;
		height: 1.35rem;
		border: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
	}

	td.self {
		background: repeating-linear-gradient(
			45deg,
			transparent 0 3px,
			color-mix(in srgb, var(--border) 50%, transparent) 3px 4px
		);
	}

	td i {
		position: absolute;
		inset: 2px;
		border-radius: 3px;
		background: #ffb347;
	}

	.vote {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		font-size: 0.62rem;
		font-weight: 800;
		color: #1a1408;
	}

	.vote:empty::before {
		content: '';
		width: 0.35rem;
		height: 0.35rem;
		border-radius: 50%;
		background: #1a1408;
	}

	.note {
		grid-column: 1 / -1;
		margin: 0;
		font-size: 0.72rem;
		color: var(--muted);
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip: rect(0 0 0 0);
		white-space: nowrap;
	}
</style>
