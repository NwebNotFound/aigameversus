<script lang="ts">
	import type { Snippet } from 'svelte';

	/** A small pill. The variant says what it means; colour is never decoration. */
	let {
		variant = 'neutral',
		title,
		children
	}: {
		variant?: 'neutral' | 'war' | 'pact' | 'tag' | 'live' | 'warn';
		title?: string;
		children: Snippet;
	} = $props();
</script>

<span class="chip {variant}" {title} data-variant={variant}>{@render children()}</span>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.05rem 0.5rem;
		border-radius: 999px;
		border: 1px solid var(--line-strong);
		font: var(--t-small);
		color: var(--muted);
		white-space: nowrap;
	}
	.war {
		color: var(--danger);
		border-color: color-mix(in srgb, var(--danger) 50%, transparent);
	}
	.pact {
		color: var(--ok);
		border-color: color-mix(in srgb, var(--ok) 50%, transparent);
	}
	.tag {
		color: var(--text);
		background: var(--raised);
		border-color: var(--line);
	}
	.live {
		color: var(--ok);
		border-color: var(--ok);
	}
	.warn {
		color: var(--brand);
		border-color: color-mix(in srgb, var(--brand) 55%, transparent);
	}
</style>
