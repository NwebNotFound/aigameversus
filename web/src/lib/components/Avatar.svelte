<script lang="ts">
	import { seatHue } from '#lib/viewer.js';

	/**
	 * A player's avatar: the initial on a lit disc, coloured by model (or seat), with one of
	 * four small marks so two players of a similar colour still differ. Original SVG.
	 */
	let {
		name,
		colourKey,
		size = 36,
		active = false,
		out = false
	}: { name: string; colourKey: string; size?: number; active?: boolean; out?: boolean } = $props();

	const hue = $derived(seatHue(colourKey));
	const mark = $derived(Math.floor(hue / 45) % 4);
	const initial = $derived([...name.trim()][0]?.toUpperCase() ?? '?');
	const id = $props.id();
</script>

<svg
	class="avatar"
	class:active
	class:out
	width={size}
	height={size}
	viewBox="0 0 40 40"
	role="img"
	aria-label={name}
	style="--hue: {hue}"
>
	<defs>
		<radialGradient id="{id}-g" cx="35%" cy="30%" r="75%">
			<stop offset="0%" stop-color="oklch(0.86 0.1 var(--hue))" />
			<stop offset="100%" stop-color="oklch(0.5 0.12 var(--hue))" />
		</radialGradient>
	</defs>
	<circle cx="20" cy="20" r="18" fill="url(#{id}-g)" />
	<circle class="ring" cx="20" cy="20" r="18.75" fill="none" stroke-width="1.5" />
	{#if mark === 0}
		<circle cx="31" cy="9" r="3" class="mark" />
	{:else if mark === 1}
		<rect x="28" y="6" width="6" height="6" rx="1" transform="rotate(45 31 9)" class="mark" />
	{:else if mark === 2}
		<path d="M31 5 L35 12 L27 12 Z" class="mark" />
	{:else}
		<path d="M27 9 h8 M31 5 v8" class="mark line" />
	{/if}
	<text x="20" y="21" text-anchor="middle" dominant-baseline="central">{initial}</text>
</svg>

<style>
	.avatar {
		flex: none;
		display: block;
		border-radius: 50%;
		transition: filter 200ms ease;
	}

	.ring {
		stroke: oklch(0.92 0.06 var(--hue) / 0.35);
	}

	.active .ring {
		stroke: var(--accent);
		stroke-width: 2.5;
	}

	.active {
		filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 70%, transparent));
	}

	.out {
		filter: grayscale(1) brightness(0.6);
	}

	.mark {
		fill: oklch(0.97 0.03 var(--hue) / 0.85);
	}

	.mark.line {
		fill: none;
		stroke: oklch(0.97 0.03 var(--hue) / 0.85);
		stroke-width: 2;
		stroke-linecap: round;
	}

	text {
		font: 700 17px var(--font);
		fill: oklch(0.2 0.04 var(--hue));
	}
</style>
