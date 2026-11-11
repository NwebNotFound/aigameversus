<script lang="ts">
	import type { Mark } from '#lib/viewer.js';
	import { chapterLabel } from '#lib/viewer.js';

	/**
	 * The replay timeline: a track with one segment per chapter (round, hand, night, day),
	 * a diamond per highlight, and the playhead. Clicking anywhere seeks.
	 */
	let {
		step,
		length,
		chapters,
		highlights,
		onseek
	}: {
		step: number;
		length: number;
		chapters: Mark[];
		highlights: Mark[];
		onseek: (step: number) => void;
	} = $props();

	let track = $state<HTMLDivElement>();
	const at = (s: number) => (length === 0 ? 0 : (s / length) * 100);
	const current = $derived(chapters.findLast((c) => c.step <= step) ?? null);
	/** Numbered chapters (rounds, hands, nights, days) get a button; the rest are ticks. */
	const named = $derived(
		chapters.flatMap((chapter) => {
			const label = chapterLabel(chapter.line);
			return label ? [{ ...chapter, label }] : [];
		})
	);
	const currentNamed = $derived(named.findLast((c) => c.step <= step) ?? null);

	function seekFrom(event: PointerEvent) {
		if (!track || length === 0) return;
		const box = track.getBoundingClientRect();
		const share = Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1);
		onseek(Math.round(share * length));
	}

	let dragging = false;
</script>

<div class="timeline">
	<div
		class="track"
		bind:this={track}
		role="slider"
		tabindex="0"
		aria-label="Replay position"
		aria-valuemin={0}
		aria-valuemax={length}
		aria-valuenow={step}
		aria-valuetext={current ? `${current.line.text}, step ${step} of ${length}` : `step ${step}`}
		data-testid="timeline"
		onpointerdown={(e) => {
			dragging = true;
			track?.setPointerCapture(e.pointerId);
			seekFrom(e);
		}}
		onpointermove={(e) => dragging && seekFrom(e)}
		onpointerup={() => (dragging = false)}
		onkeydown={(e) => {
			if (e.key === 'Home') onseek(0);
			else if (e.key === 'End') onseek(length);
			else return;
			e.preventDefault();
		}}
	>
		<div class="rail"></div>
		<div class="fill" style="width: {at(step)}%"></div>
		{#each chapters as chapter (chapter.step)}
			<span class="tick" style="left: {at(chapter.step - 1)}%"></span>
		{/each}
		{#each highlights as mark (mark.step)}
			<span
				class="diamond {mark.line.kind}"
				style="left: {at(mark.step)}%"
				title={mark.line.text}
				data-testid="highlight"
			></span>
		{/each}
		<span class="head" style="left: {at(step)}%"></span>
	</div>

	{#if named.length > 1}
		<nav class="chapters" aria-label="Chapters" data-testid="chapters">
			{#each named as chapter (chapter.step)}
				<button
					class:current={currentNamed?.step === chapter.step}
					title={chapter.line.text}
					onclick={() => onseek(chapter.step)}>{chapter.label}</button
				>
			{/each}
		</nav>
	{/if}
</div>

<style>
	.timeline {
		display: grid;
		gap: 0.5rem;
		min-width: 0;
	}

	.track {
		position: relative;
		height: 1.75rem;
		cursor: pointer;
		touch-action: none;
		border-radius: 999px;
	}

	.rail,
	.fill {
		position: absolute;
		top: 50%;
		left: 0;
		height: 6px;
		margin-top: -3px;
		border-radius: 999px;
	}

	.rail {
		right: 0;
		background: var(--surface-raised);
		border: 1px solid var(--border);
	}

	.fill {
		background: linear-gradient(
			90deg,
			color-mix(in srgb, var(--accent) 50%, transparent),
			var(--accent)
		);
	}

	.tick {
		position: absolute;
		top: 50%;
		width: 2px;
		height: 14px;
		margin: -7px 0 0 -1px;
		background: var(--muted);
		opacity: 0.55;
		pointer-events: none;
	}

	.diamond {
		position: absolute;
		top: 50%;
		width: 9px;
		height: 9px;
		margin: -4.5px 0 0 -4.5px;
		transform: translateY(-11px) rotate(45deg);
		background: var(--danger);
		border-radius: 2px;
		pointer-events: none;
	}

	.diamond.reveal {
		background: var(--accent);
	}

	.diamond.result {
		background: var(--ok);
	}

	.head {
		position: absolute;
		top: 50%;
		width: 16px;
		height: 16px;
		margin: -8px 0 0 -8px;
		border-radius: 50%;
		background: var(--text);
		box-shadow:
			0 0 0 3px var(--accent),
			0 2px 8px rgb(0 0 0 / 0.5);
		pointer-events: none;
	}

	.track:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 4px;
	}

	.chapters {
		display: flex;
		gap: 0.3rem;
		overflow-x: auto;
		scrollbar-width: thin;
		padding-bottom: 0.15rem;
	}

	.chapters button {
		flex: none;
		font: inherit;
		font-size: 0.75rem;
		font-variant-numeric: tabular-nums;
		color: var(--muted);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 6px;
		padding: 0.15rem 0.5rem;
		min-height: 1.75rem;
		cursor: pointer;
	}

	.chapters button.current {
		color: var(--bg);
		background: var(--accent);
		border-color: var(--accent);
	}
</style>
