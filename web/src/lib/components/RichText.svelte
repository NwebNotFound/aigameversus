<script lang="ts">
	import type { Seat } from '#lib/api.js';
	import Mention from '#lib/components/Mention.svelte';
	import { richText, type Inline } from '#lib/rich-text.js';
	import { colourKey, seatName } from '#lib/viewer.js';

	/**
	 * A model's words with their little markup drawn (bold, italic, lists, paragraphs and a
	 * label for each reasoning step) and seats as name chips. Built element by element from
	 * a parsed tree: nothing the model wrote is ever read as HTML.
	 */
	let { text, players }: { text: string; players: Record<string, Seat> | undefined } = $props();

	const blocks = $derived(richText(text, players));
</script>

{#snippet pieces(items: Inline[])}{#each items as item, i (i)}{#if 'br' in item}<br
			/>{:else if 'bold' in item}<strong>{@render pieces(item.bold)}</strong
			>{:else if 'italic' in item}<em>{@render pieces(item.italic)}</em
			>{:else if 'seat' in item}<Mention
				seat={item.seat}
				name={seatName(item.seat, players)}
				colourKey={colourKey(item.seat, players)}
				written={item.text}
			/>{:else}{item.text}{/if}{/each}{/snippet}

<span class="rich" data-testid="rich-text">
	{#each blocks as block, i (i)}
		{#if block.kind === 'label'}
			<span class="label" data-testid="step-label">{@render pieces(block.inline)}</span>
		{:else if block.kind === 'list'}
			<span class="list" role="list">
				{#each block.items as item, j (j)}
					<span class="item" role="listitem">{@render pieces(item)}</span>
				{/each}
			</span>
		{:else}
			<span class="para">{@render pieces(block.inline)}</span>
		{/if}
	{/each}
</span>

<style>
	.rich {
		display: grid;
		gap: 0.45rem;
	}

	.label {
		font-size: 0.75rem;
		font-style: normal;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: color-mix(in srgb, var(--thought) 65%, var(--text));
	}

	.para,
	.item {
		display: block;
	}

	.list {
		display: grid;
		gap: 0.2rem;
	}

	.item {
		position: relative;
		padding-left: 0.9rem;
	}

	.item::before {
		content: '•';
		position: absolute;
		left: 0.2rem;
		color: var(--muted);
	}
</style>
