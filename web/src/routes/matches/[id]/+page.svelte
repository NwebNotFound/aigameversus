<script lang="ts">
	import { onMount } from 'svelte';
	import type { ControlAction, LiveState, MatchEvent, Transcript } from '#lib/api.js';
	import ViewSwitch from '#lib/components/ViewSwitch.svelte';
	import WatchScreen from '#lib/components/WatchScreen.svelte';
	import { gameName } from '#lib/games.js';
	import { SPEEDS, euros, merge } from '#lib/live.js';
	import { langOf, mergeSeats } from '#lib/viewer.js';
	import type { PageProps } from './$types';

	let { data, params }: PageProps = $props();

	const view = $derived(data.view);
	/** `?view=spoiler-free` on every call, so the web server sends public data only. */
	const viewQuery = $derived(view === 'spoiler-free' ? '?view=spoiler-free' : '');

	/** The latest snapshot from /state; until the first one, what the page was loaded with. */
	let fresh = $state<LiveState | null>(null);
	const live = $derived(fresh ?? (data.result.state === 'ok' ? data.result.data : null));

	let log = $state<MatchEvent[]>([]);
	let transcript = $state<Transcript | null>(null);
	let connection = $state<'connecting' | 'live' | 'reconnecting' | 'ended' | 'missing'>(
		'connecting'
	);
	let confirmAbort = $state(false);
	let busy = $state(false);
	let problem = $state<string | null>(null);

	const status = $derived(live?.control?.paused ? 'paused' : (live?.match.status ?? 'unknown'));
	const base = $derived(`/matches/${encodeURIComponent(params.id)}`);
	const lang = $derived(live ? langOf(live.match.settings) : 'en');
	const turn = $derived(live?.board.spec?.turn);

	let refreshTimer: ReturnType<typeof setTimeout> | undefined;
	/** Board, cost, status and commentary after new turns; at most about three times a second. */
	function refreshSoon() {
		refreshTimer ??= setTimeout(async () => {
			refreshTimer = undefined;
			const join = viewQuery ? '&' : '?';
			const [state, lines] = await Promise.all([
				fetch(`${base}/state${viewQuery}`).catch(() => null),
				fetch(`${base}/transcript${viewQuery}${join}lang=${lang}`).catch(() => null)
			]);
			if (state?.ok) fresh = await state.json();
			if (lines?.ok) transcript = await lines.json();
		}, 300);
	}

	async function command(body: ControlAction) {
		busy = true;
		problem = null;
		try {
			const response = await fetch(`${base}/state${viewQuery}`, {
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
		const source = new EventSource(`${base}/stream${viewQuery}`);
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
		refreshSoon();
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
	<header class="top" aria-label="Match">
		<div class="title">
			<h1>{gameName(live.match.game)}</h1>
			<span class="pill" data-status={status} data-testid="status">
				{#if status === 'running' && connection === 'live'}<i class="dot"></i>{/if}{status}
			</span>
			<span class="muted" data-testid="connection">
				{#if connection === 'live'}live{:else if connection === 'reconnecting'}reconnecting…
				{:else if connection === 'ended'}whole log loaded{:else if connection === 'missing'}
					not found{:else}connecting…{/if}
			</span>
			<span class="total" data-testid="cost">{euros(live.cost.total_micro_eur)}</span>
		</div>
		<div class="bar">
			<ViewSwitch {view} />
			{#if view === 'spectator'}<span class="muted" data-testid="seed">seed {live.match.seed}</span
				>{/if}
		</div>
		{#if problem}<p class="problem" role="alert">{problem}</p>{/if}
	</header>

	<WatchScreen
		spec={live.board.spec}
		{view}
		events={log}
		lines={transcript?.lines ?? []}
		seats={live.match.players}
		players={mergeSeats(live.match.players, live.match.seats, transcript?.players, data.roster)}
		costs={live.cost.players}
		active={typeof turn === 'string' ? turn : null}
		placements={live.match.placements}
		ended={live.match.status === 'finished'}
	>
		{#snippet controls()}
			{#if live.control}
				<div class="controls" role="group" aria-label="Controls">
					{#if live.control.paused}
						<button class="primary" disabled={busy} onclick={() => command({ action: 'resume' })}
							>Resume</button
						>
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
			{:else if live.match.status === 'finished'}
				<a class="replay-link" href="/replays/{params.id}{viewQuery}">Watch the replay →</a>
			{/if}
		{/snippet}
	</WatchScreen>
{/if}

<style>
	.top {
		display: grid;
		gap: 0.6rem;
		padding-top: 1.25rem;
	}

	.title {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.8rem;
	}

	h1 {
		margin: 0;
		font-size: clamp(1.6rem, 4vw, 2.4rem);
	}

	.pill {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.1rem 0.65rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		font-size: 0.8rem;
	}

	.pill[data-status='running'] {
		color: var(--ok);
		border-color: var(--ok);
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

	.dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: currentColor;
		animation: pulse 1.6s ease-in-out infinite;
	}

	@keyframes pulse {
		50% {
			opacity: 0.3;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.dot {
			animation: none;
		}
	}

	.total {
		margin-left: auto;
		font-variant-numeric: tabular-nums;
		color: var(--accent);
		font-weight: 650;
	}

	.muted {
		color: var(--muted);
		font-size: 0.85rem;
	}

	.bar,
	.controls,
	.confirm {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
	}

	.controls {
		padding: 0.75rem 0.9rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
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

	button.primary {
		color: var(--bg);
		background: var(--accent);
		border-color: var(--accent);
	}

	button.danger {
		color: var(--danger);
	}

	label {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}

	.replay-link {
		color: var(--accent);
	}

	.problem {
		color: var(--danger);
	}
</style>
