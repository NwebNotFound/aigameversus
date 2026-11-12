<script lang="ts">
	import { onMount } from 'svelte';
	import type { Board, ControlAction, LiveState, MatchEvent, Transcript } from '#lib/api.js';
	import ViewSwitch from '#lib/components/ViewSwitch.svelte';
	import AnalyticsPanel from '#lib/components/analytics/AnalyticsPanel.svelte';
	import WatchScreen from '#lib/components/WatchScreen.svelte';
	import { gameName } from '#lib/games.js';
	import { SPEEDS, euros, merge } from '#lib/live.js';
	import { dwellMs, SPEEDS as PLAYBACK } from '#lib/pacing.js';
	import {
		colourKey,
		langOf,
		linesUpTo,
		mergeSeats,
		namedLines,
		nextStop,
		seatName,
		stops
	} from '#lib/viewer.js';
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
	let tab = $state<'watch' | 'analytics'>('watch');
	let busy = $state(false);
	let problem = $state<string | null>(null);

	// The playout: events arrive as fast as the models answer; the screen shows them moment by
	// moment, each for as long as the director says, so a burst of instant moves is still
	// watchable. Joining a running match starts at its newest moment (no replay of the past).
	let shown = $state(0);
	let started = $state(false);
	let playback = $state(1);
	/** When the newest event arrived, for the thinking timer while a model is asked. */
	let arrived = $state(Date.now());
	let now = $state(Date.now());

	const status = $derived(live?.control?.paused ? 'paused' : (live?.match.status ?? 'unknown'));
	const base = $derived(`/matches/${encodeURIComponent(params.id)}`);
	const lang = $derived(live ? langOf(live.match.settings) : 'en');
	const turn = $derived(live?.board.spec?.turn);
	const players = $derived(
		live
			? mergeSeats(live.match.players, live.match.seats, transcript?.players, data.roster)
			: undefined
	);

	const allLines = $derived(
		namedLines(
			transcript?.lines ?? [],
			players,
			Object.values(transcript?.players ?? {}).some((p) => p.display)
		)
	);
	const moments = $derived(stops(log, allLines, 2));
	/** The transcript covers the log up to here; the playout never runs ahead of its words. */
	const covered = $derived.by(() => {
		const last = Math.max(-1, ...allLines.map((l) => l.seq ?? -1));
		return log.filter((e) => e.seq <= last).length;
	});
	const behind = $derived(moments.filter((m) => m > shown).length);
	const atLive = $derived(shown >= log.length);
	const shownSeq = $derived(shown === 0 ? -1 : (log[shown - 1]?.seq ?? -1));

	$effect(() => {
		if (!started || shown >= log.length) return;
		const target = Math.min(nextStop(moments, shown, log.length), Math.max(covered, shown));
		if (target <= shown) return;
		const before = Math.max(0, ...moments.filter((m) => m <= shown));
		const since = before === 0 ? -1 : log[before - 1].seq;
		const showing = allLines.filter((l) => l.seq !== null && l.seq > since && l.seq <= shownSeq);
		const timer = setTimeout(() => (shown = target), dwellMs(showing, playback));
		return () => clearTimeout(timer);
	});

	// The board of the moment on screen while the playout is behind; the live board at live.
	const boards = new Map<number, Board['spec']>();
	let pastSpec = $state<Board['spec']>(null);
	$effect(() => {
		if (atLive) return;
		const at = shownSeq + 1;
		if (boards.has(at)) {
			pastSpec = boards.get(at) ?? null;
			return;
		}
		const query = view === 'spoiler-free' ? '&view=spoiler-free' : '';
		fetch(`/replays/${encodeURIComponent(params.id)}/board?events=${at}${query}`)
			.then((r) => (r.ok ? r.json() : null))
			.then((board: Board | null) => {
				if (!board) return;
				boards.set(at, board.spec);
				if (shownSeq + 1 === at) pastSpec = board.spec;
			})
			.catch(() => {});
	});

	/** Who is being asked right now, and since when: the arena's word if it sends it. */
	const thinking = $derived.by(() => {
		if (!live || !atLive || live.match.status !== 'running' || live.control?.paused) return null;
		const asking = (live.control as { asking?: { player: string; since: string }[] } | null)
			?.asking;
		if (asking?.length) {
			return { seat: asking[0].player, ms: now - Date.parse(asking[0].since) };
		}
		return typeof turn === 'string' ? { seat: turn, ms: now - arrived } : null;
	});

	/** Each player's last response time, from the decision events (spectators only). */
	const responses = $derived.by(() => {
		const last: Record<string, number> = {};
		for (const event of log.slice(0, shown)) {
			const ms = event.data.latency_ms;
			if (
				event.type === 'decision' &&
				typeof event.data.player === 'string' &&
				typeof ms === 'number'
			) {
				last[event.data.player] = ms;
			}
		}
		return last;
	});

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
			arrived = Date.now();
			if (!started) shown = log.length;
			refreshSoon();
		});
		// The backlog of a running match comes in one burst: show its end, then play out.
		const begin = setTimeout(() => {
			started = true;
			shown = log.length;
		}, 600);
		const tick = setInterval(() => (now = Date.now()), 1000);
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
			clearTimeout(begin);
			clearInterval(tick);
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
	<header class="top" aria-label="Match" data-testid="live-header" data-received={log.length}>
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
			<div class="tabs" role="tablist" aria-label="Match views">
				<button role="tab" aria-selected={tab === 'watch'} onclick={() => (tab = 'watch')}
					>Watch</button
				>
				<button
					role="tab"
					aria-selected={tab === 'analytics'}
					onclick={() => (tab = 'analytics')}
					data-testid="tab-analytics">Analytics</button
				>
			</div>
			{#if view === 'spectator'}<span class="muted" data-testid="seed">seed {live.match.seed}</span
				>{/if}
		</div>
		{#if problem}<p class="problem" role="alert">{problem}</p>{/if}
	</header>

	{#if tab === 'analytics'}
		<div class="analytics-tab">
			<AnalyticsPanel
				id={params.id}
				{view}
				version={log.length}
				names={Object.fromEntries(live.match.players.map((s) => [s, seatName(s, players)]))}
				colours={Object.fromEntries(live.match.players.map((s) => [s, colourKey(s, players)]))}
			/>
		</div>
	{:else}
		<WatchScreen
			spec={atLive ? live.board.spec : (pastSpec ?? live.board.spec)}
			{view}
			events={log.slice(0, shown)}
			lines={linesUpTo(allLines, shownSeq)}
			{thinking}
			{responses}
			seats={live.match.players}
			{players}
			costs={live.cost.players}
			active={typeof turn === 'string' ? turn : null}
			placements={live.match.placements}
			ended={live.match.status === 'finished' && atLive}
		>
			{#snippet controls()}
				<div class="playout" data-testid="playout">
					<label>
						Playback
						<select bind:value={playback} aria-label="Playback speed">
							{#each PLAYBACK as option (option.factor)}
								<option value={option.factor}>{option.label}</option>
							{/each}
						</select>
					</label>
					{#if behind > 2}
						<span class="behind" data-testid="behind">{behind} moments behind</span>
						<button onclick={() => (shown = log.length)} data-testid="jump-live"
							>Jump to live</button
						>
					{:else if live.match.status === 'running'}
						<span class="muted" data-testid="at-live">at live</span>
					{/if}
				</div>
				{#if live.control && data.readOnly}
					<p class="watch-only" data-testid="read-only">
						Watching only: this page cannot pause, speed up or abort the match.
					</p>
				{:else if live.control}
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

	.watch-only {
		margin: 0;
		font-size: 0.85rem;
		color: var(--muted);
	}

	.replay-link {
		color: var(--accent);
	}

	.problem {
		color: var(--danger);
	}
	.playout {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
		margin-bottom: 0.6rem;
	}

	.behind {
		font-size: 0.85rem;
		color: var(--accent);
	}

	.tabs {
		display: inline-flex;
		gap: 0.25rem;
	}

	.tabs button {
		font: inherit;
		font-size: 0.875rem;
		min-height: auto;
		color: var(--muted);
		background: none;
		border: 0;
		border-bottom: 2px solid transparent;
		border-radius: 0;
		padding: 0.3rem 0.5rem;
		cursor: pointer;
	}

	.tabs button[aria-selected='true'] {
		color: var(--text);
		border-bottom-color: var(--accent);
	}

	.analytics-tab {
		padding-block: 0.75rem 2rem;
	}
</style>
