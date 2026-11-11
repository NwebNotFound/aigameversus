<script lang="ts">
	import { onDestroy } from 'svelte';
	import type { TranscriptLine } from '#lib/api.js';
	import { newBeats, type Beat } from '#lib/viewer.js';

	/**
	 * The stage's reaction to key moments: a call-out with the transcript's own words at the
	 * top edge and a short light effect, one moment after another. Only what was just watched
	 * gets one: opening a match, seeking and stepping back stay quiet.
	 */
	let { lines, current = $bindable(null) }: { lines: TranscriptLine[]; current?: Beat | null } =
		$props();

	const HOLD_MS = 1400;
	let shown = $state<{ line: TranscriptLine; beat: Beat } | null>(null);
	let queue: { line: TranscriptLine; beat: Beat }[] = [];
	let timer: ReturnType<typeof setTimeout> | undefined;
	/** The newest position seen; null until the first lines arrive. */
	let newest: number | null = null;

	function next() {
		shown = queue.shift() ?? null;
		current = shown?.beat ?? null;
		timer = shown ? setTimeout(next, HOLD_MS) : undefined;
	}

	$effect(() => {
		const last = lines.findLast((line) => line.seq !== null)?.seq ?? -1;
		if (newest === null || last < newest) {
			// The first view of a match, or a step back: no drama, and nothing left queued.
			newest = last;
			queue = [];
			return;
		}
		const fresh = newBeats(lines, newest);
		newest = last;
		if (fresh.length === 0) return;
		queue.push(...fresh);
		queue = queue.slice(-3);
		if (!timer) next();
	});

	onDestroy(() => clearTimeout(timer));
</script>

<p class="sr-only" aria-live="polite" data-testid="banner-text">{shown?.line.text ?? ''}</p>
{#if shown}
	{#key shown.line.seq}
		<div class="flash {shown.beat}" aria-hidden="true"></div>
		<div class="callout {shown.beat}" data-testid="banner" data-beat={shown.beat}>
			{shown.line.text}
		</div>
	{/key}
{/if}

<style>
	.flash {
		position: absolute;
		inset: 0;
		z-index: 4;
		border-radius: inherit;
		pointer-events: none;
		animation: flash 900ms ease-out forwards;
	}

	.flash.call,
	.flash.reveal {
		box-shadow:
			inset 0 0 0 3px var(--accent),
			inset 0 0 60px rgb(240 179 90 / 0.35);
	}

	.flash.bang,
	.flash.death {
		background: radial-gradient(circle at 50% 50%, rgb(255 107 107 / 0.35), transparent 70%);
		box-shadow: inset 0 0 0 3px var(--danger);
	}

	.flash.click {
		box-shadow: inset 0 0 0 2px var(--muted);
	}

	.flash.allin,
	.flash.end {
		box-shadow:
			inset 0 0 0 3px var(--accent),
			inset 0 0 90px rgb(240 179 90 / 0.45);
	}

	.flash.win {
		box-shadow:
			inset 0 0 0 3px var(--ok),
			inset 0 0 60px rgb(110 231 168 / 0.3);
	}

	.flash.night {
		background: rgb(10 14 40 / 0.55);
		animation-duration: 1200ms;
	}

	.flash.highlight {
		box-shadow: inset 0 0 0 2px var(--accent);
	}

	@keyframes flash {
		from {
			opacity: 1;
		}
		to {
			opacity: 0;
		}
	}

	/* The transcript's words on the stage's top edge: over the frame, not over a seat. */
	.callout {
		position: absolute;
		top: 0;
		left: 50%;
		z-index: 5;
		max-width: calc(100% - 1.5rem);
		width: max-content;
		transform: translate(-50%, -50%);
		padding: 0.4rem 1rem;
		border-radius: 999px;
		background: rgb(10 8 14 / 0.9);
		border: 1px solid currentColor;
		box-shadow: 0 6px 20px rgb(0 0 0 / 0.45);
		font-size: clamp(0.85rem, 2.6vw, 1.05rem);
		font-weight: 700;
		text-align: center;
		color: var(--accent);
		pointer-events: none;
		animation: pop 250ms ease-out;
	}

	.callout.bang,
	.callout.death {
		color: var(--danger);
	}

	.callout.click,
	.callout.night {
		color: var(--text);
	}

	.callout.win {
		color: var(--ok);
	}

	@keyframes pop {
		from {
			transform: translate(-50%, -80%) scale(0.94);
			opacity: 0;
		}
		to {
			transform: translate(-50%, -50%) scale(1);
			opacity: 1;
		}
	}

	/* Reduced motion: no flashes or pops; the call-out still appears, as a static label. */
	@media (prefers-reduced-motion: reduce) {
		.flash {
			display: none;
		}

		.callout {
			animation: none;
		}
	}
</style>
