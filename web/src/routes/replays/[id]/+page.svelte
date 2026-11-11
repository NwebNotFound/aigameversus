<script lang="ts">
	import { page } from '$app/state';
	import { replaceState } from '$app/navigation';
	import type { Board } from '#lib/api.js';
	import ChroniclePanel from '#lib/components/ChroniclePanel.svelte';
	import MatchColumns from '#lib/components/MatchColumns.svelte';
	import ResultCard from '#lib/components/ResultCard.svelte';
	import { matchLang } from '#lib/event-text.js';
	import { gameName } from '#lib/games.js';
	import { describe, euros, playersOf } from '#lib/live.js';
	import { playerLabel } from '#lib/players.js';
	import {
		DEFAULT_PLAY_MS,
		PLAY_SPEEDS,
		clampStep,
		nextStep,
		shareLink,
		stepFromQuery
	} from '#lib/replay.js';
	import type { PageProps } from './$types';

	let { data, params }: PageProps = $props();

	const match = $derived(data.match.state === 'ok' ? data.match.data : null);
	const log = $derived(data.events.state === 'ok' ? data.events.data : []);

	// svelte-ignore state_referenced_locally
	let step = $state(stepFromQuery(page.url.searchParams.get('step'), log.length));
	let playing = $state(false);
	let playMs = $state(DEFAULT_PLAY_MS);
	let spoilers = $state(true);
	let copied = $state(false);
	// svelte-ignore state_referenced_locally
	let tab = $state<'replay' | 'chronicle'>(
		page.url.searchParams.get('tab') === 'chronicle' ? 'chronicle' : 'replay'
	);

	const shown = $derived(log.slice(0, step));
	const current = $derived(step > 0 ? log[step - 1] : null);
	const seats = $derived(match?.match.seats ?? null);
	const lang = $derived(matchLang(match?.match.settings));
	// What just happened, as one line under the timeline, and who did it (lit up on the board).
	const now = $derived.by(() => {
		if (!current || !match) return null;
		const line = describe(current, match.match.game, lang, seats);
		if (line.kind === 'message') return `${line.player}: “${line.text}”`;
		if (line.kind === 'thought') return spoilers ? `${line.player} thinks: ${line.text}` : null;
		if (line.kind === 'narration') return line.text;
		return line.sentence;
	});
	const active = $derived(current ? playersOf(current) : []);
	const atEnd = $derived(step >= log.length);
	const link = $derived(shareLink(page.url.origin, params.id, step));

	// The board of each step, fetched once and kept; the last one stays up while the next loads.
	const boards = new Map<number, Board['spec']>();
	let spec = $state<Board['spec']>(null);
	let boardFailed = $state(false);

	$effect(() => {
		const at = step;
		if (boards.has(at)) {
			spec = boards.get(at) ?? null;
			return;
		}
		const controller = new AbortController();
		const timer = setTimeout(() => {
			fetch(`/replays/${encodeURIComponent(params.id)}/board?events=${at}`, {
				signal: controller.signal
			})
				.then((response) => (response.ok ? response.json() : Promise.reject()))
				.then((board: Board) => {
					boards.set(at, board.spec);
					spec = board.spec;
					boardFailed = false;
				})
				.catch((error) => {
					if (error?.name !== 'AbortError') boardFailed = true;
				});
		}, 80);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});

	// Playback: one important event per tick (bookkeeping is skipped), stopping at the end.
	$effect(() => {
		if (!playing) return;
		const timer = setInterval(() => {
			if (step >= log.length) playing = false;
			else step = nextStep(log, step, 1, spoilers);
		}, playMs);
		return () => clearInterval(timer);
	});

	// The address follows the step, so reloading or copying it keeps the place.
	$effect(() => {
		const url = new URL(page.url.href);
		url.searchParams.set('step', String(step));
		if (tab === 'chronicle') url.searchParams.set('tab', 'chronicle');
		else url.searchParams.delete('tab');
		if (url.href !== page.url.href) replaceState(url, {});
	});

	function go(to: number) {
		playing = false;
		step = clampStep(to, log.length);
	}

	function togglePlay() {
		if (!playing && step >= log.length) step = 0;
		playing = !playing;
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

<a class="back" href="/replays">← Replays</a>

{#if !match || data.events.state !== 'ok'}
	<h1>Replay</h1>
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>The arena API did not answer. Is the stack running?</span>
	</div>
{:else}
	<section class="top" aria-label="Replay">
		<div class="title">
			<h1>{gameName(match.match.game)}</h1>
			<span class="pill" data-status={match.match.status}>{match.match.status}</span>
		</div>
		<p class="muted" data-testid="players">
			{match.match.players.map((seat) => playerLabel(seat, seats)).join(' · ')} · seed
			{match.match.seed} · cost
			{euros(match.cost.total_micro_eur)}
		</p>

		<div class="tabs" role="tablist" aria-label="Replay views">
			<button
				role="tab"
				aria-selected={tab === 'replay'}
				onclick={() => (tab = 'replay')}
				data-testid="tab-replay">Replay</button
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
			<label class="toggle">
				<input type="checkbox" bind:checked={spoilers} />
				Show spoilers
			</label>
		</div>

		{#if tab === 'replay'}
			<div class="timeline" role="group" aria-label="Timeline">
				<input
					type="range"
					min="0"
					max={log.length}
					value={step}
					oninput={(e) => go(e.currentTarget.valueAsNumber)}
					aria-label="Step"
					aria-valuetext="Step {step} of {log.length}"
				/>
				<div class="buttons">
					<button onclick={() => go(0)} aria-label="To the start">⏮</button>
					<button
						onclick={() => go(nextStep(log, step, -1, spoilers))}
						disabled={step === 0}
						aria-label="Previous move">◀</button
					>
					<button onclick={togglePlay} aria-label={playing ? 'Pause' : 'Play'}>
						{playing ? '❚❚' : '▶'}
					</button>
					<button
						onclick={() => go(nextStep(log, step, 1, spoilers))}
						disabled={step >= log.length}
						aria-label="Next move"
					>
						▶|
					</button>
					<button onclick={() => go(log.length)} aria-label="To the end">⏭</button>
					<label>
						Speed
						<select bind:value={playMs}>
							{#each PLAY_SPEEDS as speed (speed.ms)}
								<option value={speed.ms}>{speed.label}</option>
							{/each}
						</select>
					</label>
				</div>
				<p class="position" data-testid="position">
					Step {step} of {log.length}{#if current}: {current.type.replaceAll('_', ' ')}{/if}
				</p>
				{#if now}<p class="now" data-testid="now" aria-live="polite">{now}</p>{/if}
			</div>

			<div class="bar">
				<a
					class="button"
					href="/replays/{params.id}/export.json"
					download
					title="The whole spectator log: hidden cards, roles and the players' thoughts included"
				>
					Export JSON
				</a>
				<small class="muted export-note"> Includes hidden cards, roles and thoughts. </small>
				<span class="share">
					<input
						readonly
						value={link}
						aria-label="Share link"
						onfocus={(e) => e.currentTarget.select()}
					/>
					<button onclick={copyLink}>{copied ? 'Copied' : 'Copy link'}</button>
				</span>
			</div>
			{#if boardFailed}<p class="problem" role="status">
					The board for this step did not load.
				</p>{/if}
		{/if}
	</section>

	{#if tab === 'replay'}
		{#if atEnd && match.match.placements}
			<ResultCard placements={match.match.placements} {seats} costs={match.cost.players} />
		{/if}
		<MatchColumns
			{spec}
			{spoilers}
			events={shown}
			players={match.match.players}
			game={match.match.game}
			{lang}
			{seats}
			{active}
		/>
	{:else}
		<ChroniclePanel id={params.id} {spoilers} onreveal={() => (spoilers = true)} />
	{/if}
{/if}

<style>
	.back {
		display: inline-block;
		margin-top: 1rem;
		color: var(--muted);
	}

	.top {
		display: grid;
		gap: 0.75rem;
		padding-block: 0.75rem 0.25rem;
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

	.muted {
		margin: 0;
		color: var(--muted);
	}

	.pill {
		padding: 0.1rem 0.7rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		font-size: 0.85rem;
	}

	.tabs {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		border-bottom: 1px solid var(--border);
	}

	.tabs button {
		border-radius: 8px 8px 0 0;
		border-bottom-color: transparent;
	}

	.tabs .toggle {
		margin-left: auto;
	}

	.tabs button[aria-selected='true'] {
		color: var(--accent);
		border-color: var(--accent);
		border-bottom-color: var(--bg);
	}

	.timeline {
		display: grid;
		gap: 0.5rem;
		padding: 0.75rem 1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	input[type='range'] {
		width: 100%;
		accent-color: var(--accent);
	}

	.buttons,
	.bar,
	.share {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
	}

	.bar {
		gap: 0.75rem 1.5rem;
	}

	.position {
		margin: 0;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
	}

	button,
	select,
	.button,
	.share input {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.35rem 0.8rem;
		min-height: 2.25rem;
		text-decoration: none;
	}

	.share input {
		width: min(26rem, 100%);
		color: var(--muted);
	}

	.share {
		flex: 1 1 18rem;
		min-width: 0;
	}

	button:not(:disabled),
	.button {
		cursor: pointer;
	}

	button:disabled {
		opacity: 0.5;
	}

	label {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}

	.problem {
		margin: 0;
		color: var(--danger);
	}

	.now {
		margin: 0;
		padding: 0.5rem 0.75rem;
		border-radius: 8px;
		background: var(--surface-raised);
		border-left: 3px solid var(--accent);
		font-size: 1.05rem;
	}
</style>
