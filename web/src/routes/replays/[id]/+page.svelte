<script lang="ts">
	import { page } from '$app/state';
	import { goto, replaceState } from '$app/navigation';
	import type { Board } from '#lib/api.js';
	import ChroniclePanel from '#lib/components/ChroniclePanel.svelte';
	import AnalyticsPanel from '#lib/components/analytics/AnalyticsPanel.svelte';
	import Timeline from '#lib/components/Timeline.svelte';
	import ViewSwitch from '#lib/components/ViewSwitch.svelte';
	import WatchScreen from '#lib/components/WatchScreen.svelte';
	import { gameName } from '#lib/games.js';
	import { euros } from '#lib/live.js';
	import { dwellMs, SPEEDS } from '#lib/pacing.js';
	import { clampStep, shareLink, stepFromQuery } from '#lib/replay.js';
	import {
		linesUpTo,
		marks,
		nextStop,
		previousStop,
		stops,
		mergeSeats,
		namedLines,
		seatName,
		colourKey
	} from '#lib/viewer.js';
	import type { PageProps } from './$types';

	let { data, params }: PageProps = $props();

	const view = $derived(data.view);
	const match = $derived(data.match.state === 'ok' ? data.match.data : null);
	const log = $derived(data.events.state === 'ok' ? data.events.data : []);
	const transcript = $derived(data.transcript.state === 'ok' ? data.transcript.data : null);
	const players = $derived(
		match
			? mergeSeats(match.match.players, match.match.seats, transcript?.players, data.roster)
			: undefined
	);
	const lines = $derived(
		namedLines(
			transcript?.lines ?? [],
			players,
			Object.values(transcript?.players ?? {}).some((p) => p.display)
		)
	);

	// svelte-ignore state_referenced_locally
	let step = $state(stepFromQuery(page.url.searchParams.get('step'), log.length));
	let playing = $state(false);
	let speed = $state(1);
	let highlightsOnly = $state(false);
	let copied = $state(false);
	// svelte-ignore state_referenced_locally
	let tab = $state<'replay' | 'analytics' | 'chronicle'>(
		(['analytics', 'chronicle'] as const).find((t) => t === page.url.searchParams.get('tab')) ??
			'replay'
	);

	/** Position in the full log after the shown events: what the arena's board needs. */
	const logPosition = $derived(step === 0 ? 0 : (log[step - 1]?.seq ?? -1) + 1);
	const shownLines = $derived(linesUpTo(lines, step === 0 ? -1 : (log[step - 1]?.seq ?? -1)));
	const shownEvents = $derived(log.slice(0, step));
	const timeline = $derived(marks(log, lines));
	const moments = $derived(stops(log, lines, 2));
	const highlights = $derived(stops(log, lines, 3));
	// The caption tells the latest moment; the final ranking is the result card's.
	const caption = $derived(
		shownLines.findLast(
			(line) => line.importance > 1 && line.kind !== 'info' && line.raw?.type !== 'match_finished'
		)
	);
	const link = $derived(shareLink(page.url.origin, params.id, step, view));

	// Switching the view loads another log (spoiler-free has the public events only) into
	// the same page: keep the place by the event shown, not by the step number.
	// svelte-ignore state_referenced_locally
	let previousLog = log;
	$effect.pre(() => {
		const next = log;
		if (next === previousLog) return;
		const shownSeq = step > 0 ? previousLog[Math.min(step, previousLog.length) - 1]?.seq : null;
		previousLog = next;
		step =
			shownSeq === null || shownSeq === undefined
				? clampStep(step, next.length)
				: next.filter((event) => event.seq <= shownSeq).length;
	});

	// The board of each step and view, fetched once and kept; the last one stays up while the
	// next loads. The view is part of the key: a spoiler-free page never shows a spectator board.
	const boards = new Map<string, Board['spec']>();
	let spec = $state<Board['spec']>(null);
	/** The view the shown board was fetched for. */
	// svelte-ignore state_referenced_locally
	let specView = view;
	let boardFailed = $state(false);

	$effect(() => {
		const at = logPosition;
		const nation = page.url.searchParams.get('nation');
		const query =
			view === 'spoiler-free'
				? `&view=spoiler-free${nation ? `&nation=${encodeURIComponent(nation)}` : ''}`
				: '';
		const key = `${view}:${nation ?? ''}:${at}`;
		if (boards.has(key)) {
			spec = boards.get(key) ?? null;
			return;
		}
		if (specView !== view) {
			spec = null;
			specView = view;
		}
		const controller = new AbortController();
		const timer = setTimeout(() => {
			fetch(`/replays/${encodeURIComponent(params.id)}/board?events=${at}${query}`, {
				signal: controller.signal
			})
				.then((response) => (response.ok ? response.json() : Promise.reject()))
				.then((board: Board) => {
					boards.set(key, board.spec);
					spec = board.spec;
					boardFailed = false;
				})
				.catch((error) => {
					if (error?.name !== 'AbortError') boardFailed = true;
				});
		}, 60);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});

	// Playback: moment to moment (bookkeeping is skipped), or highlight to highlight. Each
	// moment stays as long as the playout director says for what it shows (reading time for
	// words, longer for highlights), not as long as the models took: replays run in
	// normalised time.
	$effect(() => {
		if (!playing) return;
		const at = step;
		const from = at === 0 ? -1 : log[at - 1].seq;
		const before = previousStop(highlightsOnly ? highlights : moments, at);
		const since = before === 0 ? -1 : log[before - 1].seq;
		const showing = lines.filter((l) => l.seq !== null && l.seq > since && l.seq <= from);
		const hold = at === 0 ? 300 : dwellMs(showing, speed);
		const timer = setTimeout(() => {
			if (step >= log.length) playing = false;
			else step = nextStop(highlightsOnly ? highlights : moments, step, log.length);
		}, hold);
		return () => clearTimeout(timer);
	});

	// The address follows the step, so reloading or copying it keeps the place.
	$effect(() => {
		const url = new URL(page.url.href);
		url.searchParams.set('step', String(step));
		if (tab === 'replay') url.searchParams.delete('tab');
		else url.searchParams.set('tab', tab);
		if (url.href !== page.url.href) replaceState(url, {});
	});

	/** From a chart: show the replay at the event at `seq`, on the Watch tab. */
	function jumpToSeq(seq: number) {
		const at = log.findIndex((event) => event.seq === seq);
		if (at < 0) return;
		go(at + 1);
		tab = 'replay';
	}

	function go(to: number) {
		playing = false;
		step = clampStep(to, log.length);
	}

	function togglePlay() {
		if (!playing && step >= log.length) step = 0;
		playing = !playing;
	}

	function onkeydown(event: KeyboardEvent) {
		const target = event.target as HTMLElement | null;
		if (tab !== 'replay' || target?.closest('input, select, textarea, [role="slider"]')) return;
		const chapterSteps = timeline.chapters.map((c) => c.step);
		if (event.key === ' ') togglePlay();
		else if (event.key === 'ArrowRight' && event.shiftKey)
			go(nextStop(chapterSteps, step, log.length));
		else if (event.key === 'ArrowLeft' && event.shiftKey) go(previousStop(chapterSteps, step));
		else if (event.key === 'ArrowRight') go(nextStop(moments, step, log.length));
		else if (event.key === 'ArrowLeft') go(previousStop(moments, step));
		else return;
		event.preventDefault();
	}

	/** The chronicle with spoilers is a spectator-view page load. */
	function revealChronicle() {
		const url = new URL(page.url.href);
		url.searchParams.delete('view');
		url.searchParams.set('tab', 'chronicle');
		goto(url);
	}

	async function copyLink() {
		try {
			await navigator.clipboard.writeText(link);
			copied = true;
			setTimeout(() => (copied = false), 1500);
		} catch {
			copied = false;
		}
	}
</script>

<svelte:head>
	<title>{match ? `${gameName(match.match.game)} replay` : 'Replay'} · AIGameVersus</title>
</svelte:head>

<svelte:window {onkeydown} />

<a class="back" href="/replays">← Replays</a>

{#if !match || data.events.state !== 'ok'}
	<h1>Replay</h1>
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>The arena API did not answer. Is the stack running?</span>
	</div>
{:else}
	<header class="top" aria-label="Replay">
		<div class="title">
			<h1>{gameName(match.match.game)}</h1>
			<span class="pill" data-status={match.match.status}>replay · {match.match.status}</span>
			<span class="total" data-testid="cost">{euros(match.cost.total_micro_eur)}</span>
		</div>
		<div class="bar">
			<ViewSwitch {view} />
			<div class="tabs" role="tablist" aria-label="Replay views">
				<button
					role="tab"
					aria-selected={tab === 'replay'}
					onclick={() => (tab = 'replay')}
					data-testid="tab-replay">Watch</button
				>
				<button
					role="tab"
					aria-selected={tab === 'analytics'}
					onclick={() => {
						playing = false;
						tab = 'analytics';
					}}
					data-testid="tab-analytics">Report</button
				>
				<button
					role="tab"
					aria-selected={tab === 'chronicle'}
					onclick={() => {
						playing = false;
						tab = 'chronicle';
					}}
					data-testid="tab-chronicle">Chronicle</button
				>
			</div>
			<details class="more">
				<summary aria-label="More">⋯</summary>
				<div class="menu">
					<button onclick={copyLink}>{copied ? 'Link copied' : 'Copy link to this moment'}</button>
					{#if view === 'spectator'}
						<a
							href="/replays/{params.id}/export.json"
							download
							data-testid="export"
							title="The whole spectator log: hidden cards, roles and thoughts included"
							>Export JSON</a
						>
						<span class="muted" data-testid="seed">Seed {match.match.seed}</span>
					{/if}
				</div>
			</details>
		</div>
		{#if data.transcript.state !== 'ok'}
			<p class="problem" role="status">The commentary did not load; the board still steps.</p>
		{/if}
	</header>

	{#if tab === 'replay'}
		<WatchScreen
			{spec}
			{view}
			events={shownEvents}
			lines={shownLines}
			seats={match.match.players}
			{players}
			costs={match.cost.players}
			active={typeof spec?.turn === 'string' ? spec.turn : null}
			placements={match.match.placements}
			ended={match.match.status === 'finished' && step === log.length}
		>
			{#snippet controls()}
				<div class="player" role="group" aria-label="Replay controls">
					<p class="caption" data-testid="caption" aria-live="polite">
						{caption?.text ?? 'Before the first move.'}
					</p>
					<Timeline
						{step}
						length={log.length}
						chapters={timeline.chapters}
						highlights={timeline.highlights}
						onseek={go}
					/>
					<div class="buttons">
						<button onclick={() => go(0)} aria-label="To the start">⏮</button>
						<button
							onclick={() => go(previousStop(moments, step))}
							disabled={step === 0}
							aria-label="Previous moment">◀</button
						>
						<button class="play" onclick={togglePlay} aria-label={playing ? 'Pause' : 'Play'}>
							{playing ? '❚❚' : '▶'}
						</button>
						<button
							onclick={() => go(nextStop(moments, step, log.length))}
							disabled={step >= log.length}
							aria-label="Next moment">▶</button
						>
						<button onclick={() => go(log.length)} aria-label="To the end">⏭</button>
						<label>
							<span class="sr-only">Speed</span>
							<select bind:value={speed} aria-label="Speed">
								{#each SPEEDS as option (option.factor)}
									<option value={option.factor}>{option.label}</option>
								{/each}
							</select>
						</label>
						<label class="toggle">
							<input type="checkbox" bind:checked={highlightsOnly} />
							Highlights only
						</label>
						<span class="position" data-testid="position">Step {step} of {log.length}</span>
					</div>
					{#if boardFailed}<p class="problem" role="status">
							The board for this moment did not load.
						</p>{/if}
				</div>
			{/snippet}
		</WatchScreen>
	{:else if tab === 'analytics'}
		<div class="analytics-tab">
			<p class="where" data-testid="analytics-step">
				At step {step} of {log.length}{#if caption}: {caption.text}{/if}
			</p>
			<AnalyticsPanel
				id={params.id}
				{view}
				lastSeq={step === 0 ? -1 : (log[step - 1]?.seq ?? null)}
				names={Object.fromEntries(match.match.players.map((s) => [s, seatName(s, players)]))}
				colours={Object.fromEntries(match.match.players.map((s) => [s, colourKey(s, players)]))}
				costs={match.cost.players}
				onjump={jumpToSeq}
			/>
		</div>
	{:else}
		<ChroniclePanel id={params.id} spoilers={view === 'spectator'} onreveal={revealChronicle} />
	{/if}
{/if}

<style>
	.back {
		display: inline-block;
		margin-top: 1rem;
		color: var(--muted);
		font-size: 0.9rem;
	}

	.top {
		display: grid;
		gap: 0.6rem;
		padding-top: 0.5rem;
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
		padding: 0.1rem 0.65rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		font-size: 0.8rem;
		color: var(--muted);
	}

	.total {
		margin-left: auto;
		font-variant-numeric: tabular-nums;
		color: var(--accent);
		font-weight: 650;
	}

	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
	}

	.tabs {
		display: inline-flex;
		gap: 0.25rem;
	}

	.tabs button {
		font: inherit;
		font-size: 0.875rem;
		color: var(--muted);
		background: none;
		border: 0;
		border-bottom: 2px solid transparent;
		padding: 0.3rem 0.5rem;
		cursor: pointer;
	}

	.tabs button[aria-selected='true'] {
		color: var(--text);
		border-bottom-color: var(--accent);
	}

	.more {
		position: relative;
		margin-left: auto;
	}

	.more summary {
		list-style: none;
		cursor: pointer;
		padding: 0.2rem 0.7rem;
		border-radius: 8px;
		border: 1px solid var(--border);
		background: var(--surface);
		font-size: 1.1rem;
		line-height: 1.4;
	}

	.more summary::-webkit-details-marker {
		display: none;
	}

	.menu {
		position: absolute;
		right: 0;
		top: calc(100% + 0.35rem);
		z-index: 5;
		display: grid;
		gap: 0.4rem;
		min-width: 14rem;
		padding: 0.6rem;
		border-radius: 10px;
		background: var(--surface-raised);
		border: 1px solid var(--border);
		box-shadow: 0 10px 30px rgb(0 0 0 / 0.4);
	}

	.menu a,
	.menu button {
		font: inherit;
		font-size: 0.875rem;
		text-align: left;
		color: var(--text);
		background: none;
		border: 0;
		padding: 0.25rem 0.2rem;
		cursor: pointer;
		text-decoration: none;
	}

	.muted {
		color: var(--muted);
		font-size: 0.8rem;
	}

	.player {
		display: grid;
		gap: 0.6rem;
		padding: 0.75rem 0.9rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	/* Room for two lines; a longer moment wraps and is never cut off. */
	.caption {
		margin: 0;
		min-height: 3em;
		font-size: 0.95rem;
		line-height: 1.5;
		overflow-wrap: anywhere;
	}

	.buttons {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
	}

	.buttons button,
	select {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.3rem 0.7rem;
		min-height: 2.25rem;
		min-width: 2.5rem;
		cursor: pointer;
	}

	.buttons button.play {
		color: var(--bg);
		background: var(--accent);
		border-color: var(--accent);
		min-width: 3rem;
	}

	.buttons button:disabled {
		opacity: 0.45;
		cursor: default;
	}

	.toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.85rem;
		color: var(--muted);
	}

	.position {
		margin-left: auto;
		font-size: 0.8rem;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}

	.problem {
		margin: 0;
		color: var(--danger);
	}
	.analytics-tab {
		display: grid;
		gap: 0.6rem;
		padding-block: 0.75rem 2rem;
	}

	.where {
		margin: 0;
		font-size: 0.875rem;
		color: var(--muted);
	}
</style>
