<script lang="ts">
	import Avatar from '#lib/components/Avatar.svelte';

	/**
	 * A seat a player named in their own words ("p2"), drawn as that seat's name chip: its
	 * avatar and display name in its colour. The id the model wrote is in the tooltip.
	 */
	let {
		seat,
		name,
		colourKey,
		written
	}: { seat: string; name: string; colourKey: string; written: string } = $props();
</script>

<span class="mention" data-testid="mention" data-seat={seat} title="{written} in the model's words">
	<Avatar {name} {colourKey} size={16} />
	<span>{name}</span>
</span>

<style>
	.mention {
		display: inline-flex;
		align-items: center;
		gap: 0.2rem;
		padding: 0 0.35rem 0 0.1rem;
		border-radius: 999px;
		background: var(--surface);
		border: 1px solid var(--border);
		font-size: 0.85em;
		font-style: normal;
		font-weight: 600;
		line-height: 1.35;
		vertical-align: baseline;
		white-space: nowrap;
	}
</style>
