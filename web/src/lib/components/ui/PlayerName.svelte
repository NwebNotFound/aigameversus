<script lang="ts">
	import type { Identity } from '#lib/players.js';
	import PlayerMark from './PlayerMark.svelte';

	/** A player as text: emblem and short name in the player's colour; the full name on hover. */
	let { who, name, full }: { who: Identity; name: string; full?: string } = $props();
</script>

<span class="player" style="--who: {who.colour}" title={full ?? name} data-slot={who.slot}>
	<PlayerMark {who} size={11} />
	<span class="name">{name}</span>
</span>

<style>
	.player {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		min-width: 0;
		max-width: 100%;
	}

	.name {
		color: var(--who);
		font-weight: 600;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
</style>
