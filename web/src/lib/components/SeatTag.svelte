<script lang="ts">
	import { seatNumber } from '#lib/viewer.js';

	/**
	 * A seat's name on a board: the display name large, the seat number as a small badge
	 * (the only place a seat id appears) and, if given, the model or vendor line under it.
	 */
	let {
		seat,
		name,
		sub = null,
		compact = false
	}: { seat: string; name: string; sub?: string | null; compact?: boolean } = $props();
</script>

<span class="tag" class:compact data-testid="seat-tag">
	<span class="top">
		<span class="badge" data-testid="seat-badge" title="Seat {seatNumber(seat)}"
			>{seatNumber(seat)}</span
		>
		<strong class="name">{name}</strong>
	</span>
	{#if sub}<small class="sub">{sub}</small>{/if}
</span>

<style>
	.tag {
		display: grid;
		justify-items: center;
		min-width: 0;
		line-height: 1.15;
	}

	.top {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		max-width: 100%;
	}

	.badge {
		flex: none;
		display: inline-grid;
		place-items: center;
		min-width: 1.1rem;
		height: 1.1rem;
		padding: 0 0.2rem;
		border-radius: 4px;
		background: var(--surface-raised);
		border: 1px solid var(--border);
		color: var(--muted);
		font-size: 0.75rem;
		font-weight: 650;
		font-variant-numeric: tabular-nums;
	}

	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.95rem;
	}

	.sub {
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 0.75rem;
		color: var(--muted);
	}

	.compact .name {
		font-size: 0.8rem;
	}
</style>
