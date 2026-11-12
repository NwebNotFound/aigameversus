<script lang="ts">
	// A rating built on few rated games: the arena says how many it wants (PROVISIONAL_GAMES).
	let { limit }: { limit: number } = $props();
</script>

<span
	class="provisional"
	data-testid="provisional"
	title="fewer than {limit} rated games: the rating is not reliable yet"
>
	provisional
</span>

<style>
	.provisional {
		margin-left: 0.4rem;
		padding: 0.05rem 0.4rem;
		border: 1px dashed var(--muted);
		border-radius: 999px;
		color: var(--muted);
		font-size: 0.7rem;
		font-weight: 400;
		letter-spacing: 0.02em;
		white-space: nowrap;
		cursor: help;
	}
</style>
