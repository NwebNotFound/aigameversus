<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * A table that scrolls inside its card, with a fade at the cut edge. Numbers in it use
	 * the `num` class (mono, right aligned).
	 */
	let { label, testid, children }: { label: string; testid?: string; children: Snippet } = $props();
</script>

<div class="scroll" data-testid={testid}>
	<table aria-label={label}>
		{@render children()}
	</table>
</div>

<style>
	.scroll {
		overflow-x: auto;
		mask-image: linear-gradient(to right, #000 calc(100% - 1.25rem), transparent);
		padding-right: 1rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font: var(--t-small);
	}
	table :global(th),
	table :global(td) {
		padding: 0.4rem 0.5rem;
		text-align: left;
		border-top: 1px solid var(--line);
		white-space: nowrap;
	}
	table :global(thead th) {
		border-top: 0;
		font: var(--t-caption);
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--muted);
	}
	table :global(.num) {
		text-align: right;
	}
</style>
