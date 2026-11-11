<script lang="ts">
	import { onMount } from 'svelte';
	import type { ControlAction, LiveState, MatchEvent } from '#lib/api.js';
	import Board from '#lib/components/Board.svelte';
	import { gameName } from '#lib/games.js';
	import { SPEEDS, columnOf, describe, euros, merge, playersOf } from '#lib/live.js';
	import type { PageProps } from './$types';

	let { data, params }: PageProps = $props();

	/** The latest snapshot from /state; until the first one, what the page was loaded with. */
	let fresh = $state<LiveState | null>(null);
	const live = $derived(fresh ?? (data.result.state === 'ok' ? data.result.data : null));

	let log = $state<MatchEvent[]>([]);
	let connection = $state<'connecting' | 'live' | 'reconnecting' | 'ended' | 'missing'>(
		'connecting'
	);
	let spoilers = $state(true);
	let player = $state('all');
	let confirmAbort = $state(false);
	let busy = $state(false);
	let problem = $state<string | null>(null);

	const status = $derived(live?.control?.paused ? 'paused' : (live?.match.status ?? 'unknown'));
	const publicLines = $derived(log.filter((e) => columnOf(e) === 'public').toReversed());
	const behindLines = $derived(
		log
			.filter((e) => columnOf(e) === 'behind')
			.filter((e) => player === 'all' || playersOf(e).includes(player))
			.toReversed()
	);

	const stateUrl = $derived(`/matches/${encodeURIComponent(params.id)}/state`);

	let refreshTimer: ReturnType<typeof setTimeout> | undefined;
	/** Board, cost and status after new turns; at most about three times a second. */
	function refreshSoon() {
		refreshTimer ??= setTimeout(async () => {
			refreshTimer = undefined;
			const response = await fetch(stateUrl).catch(() => null);
			if (response?.ok) fresh = await response.json();
		}, 300);
	}

	async function command(body: ControlAction) {
		busy = true;
		problem = null;
		try {
			const response = await fetch(stateUrl, {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify(body)
			});
			if (response.ok) fresh = await response.json();
			else problem = `The arena did not take the command (${response.status}).`;
		} catch {
			problem = 'The web server could not be reached.';
		} finally {
			busy = false;
			confirmAbort = false;
		}
	}

	onMount(() => {
		const source = new EventSource(`/matches/${encodeURIComponent(params.id)}/stream`);
		source.onopen = () => (connection = 'live');
		source.onerror = () => {
			if (connection !== 'ended' && connection !== 'missing') connection = 'reconnecting';
		};
		source.addEventListener('event', (message) => {
			log = merge(log, [JSON.parse(message.data)]);
			refreshSoon();
		});
		for (const [type, state] of [
			['end', 'ended'],
			['missing', 'missing']
		] as const) {
			source.addEventListener(type, () => {
				connection = state;
				source.close();
				refreshSoon();
			});
		}
		return () => {
			source.close();
			clearTimeout(refreshTimer);
		};
	});
</script>

<svelte:head>
	<title>{live ? gameName(live.match.game) : 'Match'} · AIGameVersus</title>
</svelte:head>

{#if data.result.state === 'unreachable' || !live}
	<h1>Match</h1>
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>
			The arena API did not answer ({data.result.state === 'unreachable'
				? data.result.reason
				: 'no data'}). Is the stack running?
		</span>
	</div>
{:else}
	<section class="top" aria-label="Match">
		<div class="title">
			<h1>{gameName(live.match.game)}</h1>
			<span class="pill" data-status={status} data-testid="status">{status}</span>
			<span class="muted" data-testid="connection">
				{#if connection === 'live'}live{:else if connection === 'reconnecting'}reconnecting…
				{:else if connection === 'ended'}whole log loaded{:else if connection === 'missing'}
					not found{:else}connecting…{/if}
			</span>
		</div>
		<p class="muted">
			{live.match.players.join(' · ')} · seed {live.match.seed}
		</p>

		<div class="bar">
			{#if live.control}
				<div class="controls" role="group" aria-label="Controls">
					{#if live.control.paused}
						<button disabled={busy} onclick={() => command({ action: 'resume' })}>Resume</button>
					{:else}
						<button disabled={busy} onclick={() => command({ action: 'pause' })}>Pause</button>
					{/if}
					<label>
						Speed
						<select
							disabled={busy}
							value={live.control.turn_delay}
							onchange={(e) =>
								command({ action: 'speed', turn_delay: Number(e.currentTarget.value) })}
						>
							{#if !SPEEDS.some((s) => s.turn_delay === live.control?.turn_delay)}
								<option value={live.control.turn_delay}>{live.control.turn_delay} s</option>
							{/if}
							{#each SPEEDS as speed (speed.turn_delay)}
								<option value={speed.turn_delay}>{speed.label} ({speed.turn_delay} s)</option>
							{/each}
						</select>
					</label>
					{#if confirmAbort}
						<span class="confirm">
							Abort for good?
							<button class="danger" disabled={busy} onclick={() => command({ action: 'abort' })}>
								Yes, abort
							</button>
							<button disabled={busy} onclick={() => (confirmAbort = false)}>No</button>
						</span>
					{:else}
						<button class="danger" disabled={busy} onclick={() => (confirmAbort = true)}>
							Abort
						</button>
					{/if}
				</div>
			{/if}
			<label class="toggle">
				<input type="checkbox" bind:checked={spoilers} />
				Show spoilers
			</label>
			<div class="cost" data-testid="cost">
				<span>Cost <strong>{euros(live.cost.total_micro_eur)}</strong></span>
				{#each Object.entries(live.cost.players) as [name, micro] (name)}
					<span class="muted">{name} {euros(micro)}</span>
				{/each}
			</div>
		</div>
		{#if problem}<p class="problem" role="alert">{problem}</p>{/if}
	</section>

	<div class="columns">
		<section aria-labelledby="board-title">
			<h2 id="board-title">Board</h2>
			<Board spec={live.board.spec} {spoilers} events={log} />
		</section>

		<section aria-labelledby="public-title">
			<h2 id="public-title">Public</h2>
			{#if publicLines.length === 0}
				<p class="muted">Nothing public yet.</p>
			{/if}
			<ol class="feed" data-testid="public-feed">
				{#each publicLines as event (event.seq)}
					{@render line(event)}
				{/each}
			</ol>
		</section>

		<section aria-labelledby="behind-title">
			<h2 id="behind-title">Behind the scenes</h2>
			{#if spoilers}
				<label class="filter">
					Player
					<select bind:value={player}>
						<option value="all">All players</option>
						{#each live.match.players as name (name)}
							<option value={name}>{name}</option>
						{/each}
					</select>
				</label>
				<ol class="feed" data-testid="behind-feed">
					{#each behindLines as event (event.seq)}
						{@render line(event)}
					{/each}
				</ol>
			{:else}
				<div class="notice" role="status" data-testid="spoilers-off">
					<strong>Spoilers off</strong>
					<span>Thoughts, hands and private messages stay hidden, so you can guess along.</span>
				</div>
			{/if}
		</section>
	</div>
{/if}

{#snippet line(event: MatchEvent)}
	{@const shown = describe(event)}
	<li data-seq={event.seq} data-kind={shown.kind} data-players={playersOf(event).join(' ')}>
		{#if shown.kind === 'message'}
			<strong>{shown.player}</strong>
			<q>{shown.text}</q>
		{:else if shown.kind === 'thought'}
			<strong>{shown.player}</strong> <span class="muted">thinks</span>
			<em>{shown.text}</em>
		{:else if shown.kind === 'narration'}
			<span class="narration">{shown.text}</span>
		{:else}
			{#if shown.player}<strong>{shown.player}</strong>{/if}
			<span>{shown.title}</span>
			{#if shown.details}<small class="muted">{shown.details}</small>{/if}
		{/if}
	</li>
{/snippet}

<style>
	.top {
		padding-block: 1.25rem 0.5rem;
	}

	.title {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.9rem;
	}

	h1 {
		margin: 0;
		font-size: clamp(1.6rem, 5vw, 2.4rem);
	}

	h2 {
		font-size: 0.95rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--muted);
		margin: 0 0 0.75rem;
	}

	.pill {
		padding: 0.1rem 0.7rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		font-size: 0.85rem;
	}

	.pill[data-status='running'] {
		color: #7ad69a;
		border-color: #7ad69a;
	}

	.pill[data-status='paused'] {
		color: var(--accent);
		border-color: var(--accent);
	}

	.pill[data-status='aborted'],
	.pill[data-status='failed'] {
		color: var(--danger);
		border-color: var(--danger);
	}

	.muted {
		color: var(--muted);
	}

	.bar,
	.controls,
	.cost,
	.confirm {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.9rem;
	}

	.bar {
		gap: 0.75rem 1.5rem;
	}

	button,
	select {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.35rem 0.8rem;
		min-height: 2.25rem;
	}

	button:not(:disabled) {
		cursor: pointer;
	}

	button.danger {
		color: var(--danger);
	}

	label {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}

	.problem {
		color: var(--danger);
	}

	.columns {
		display: grid;
		gap: var(--gap);
		padding-block: 1rem 2rem;
	}

	.columns > section {
		min-width: 0;
		padding: 1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	@media (min-width: 64rem) {
		.columns {
			grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr) minmax(0, 1fr);
			align-items: start;
		}

		.feed {
			max-height: 70vh;
			overflow-y: auto;
		}
	}

	.filter {
		margin-bottom: 0.75rem;
	}

	.feed {
		display: grid;
		gap: 0.4rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.feed li {
		display: flex;
		flex-wrap: wrap;
		gap: 0.15rem 0.45rem;
		padding: 0.45rem 0.6rem;
		border-radius: 8px;
		background: var(--surface-raised);
		overflow-wrap: anywhere;
	}

	.feed li[data-kind='message'] {
		border-left: 3px solid var(--accent-2);
	}

	.feed li[data-kind='thought'] {
		border-left: 3px solid var(--accent);
	}

	.feed small {
		flex-basis: 100%;
	}

	.narration {
		font-style: italic;
	}
</style>
