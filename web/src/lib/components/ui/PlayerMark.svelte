<script lang="ts">
	import { shapePath, type Identity } from '#lib/players.js';

	/** A player's emblem: their slot's colour and shape (lib/players.ts), 10 to 16 px. */
	let { who, size = 12, title }: { who: Identity; size?: number; title?: string } = $props();
</script>

<svg
	class="mark"
	width={size}
	height={size}
	viewBox="-8 -8 16 16"
	role={title ? 'img' : undefined}
	aria-hidden={title ? undefined : 'true'}
	aria-label={title}
	data-shape={who.shape}
	data-slot={who.slot}
>
	<path d={shapePath(who.shape, 6)} fill={who.colour} stroke="var(--bg)" stroke-width="1.2" />
</svg>

<style>
	.mark {
		flex: none;
		vertical-align: -0.1em;
	}
</style>
