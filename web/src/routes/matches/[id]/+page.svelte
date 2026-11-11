<script lang="ts">
	import { onMount } from 'svelte';
	import type { ControlAction, LiveState, MatchEvent } from '#lib/api.js';
	import MatchColumns from '#lib/components/MatchColumns.svelte';
	import ResultCard from '#lib/components/ResultCard.svelte';
	import { playerLabel } from '#lib/players.js';
	import { matchLang } from '#lib/event-text.js';
	import { gameName } from '#lib/games.js';
	import { SPEEDS, euros, merge, playersOf } from '#lib/live.js';
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
	let confirmAbort = $state(false);
	let busy = $state(false);
	let problem = $state<string | null>(null);

	const status = $derived(live?.control?.paused ? 'paused' : (live?.match.status ?? 'unknown'));

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
			{live.match.players.map((seat) => playerLabel(seat, live.match.seats)).join(' · ')} · seed
			{live.match.seed}
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

	{#if live.match.status === 'finished' && live.match.placements}
		<ResultCard
			placements={live.match.placements}
			seats={live.match.seats}
			costs={live.cost.players}
		/>
	{/if}
	<MatchColumns
		spec={live.board.spec}
		{spoilers}
		events={log}
		players={live.match.players}
		game={live.match.game}
		lang={matchLang(live.match.settings)}
		seats={live.match.seats}
		active={log.length ? playersOf(log[log.length - 1]) : []}
	/>
{/if}

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
</style>
