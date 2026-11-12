<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * Every analytics card asks a question as its title and answers it in one line under it;
	 * the chart or table supports the answer.
	 */
	let {
		question,
		answer,
		testid,
		children
	}: { question: string; answer?: string | null; testid?: string; children?: Snippet } = $props();
</script>

<section class="card" data-testid={testid}>
	<h3 class="question">{question}</h3>
	{#if answer}<p class="answer">{answer}</p>{/if}
	{#if children}<div class="body">{@render children()}</div>{/if}
</section>

<style>
	.card {
		min-width: 0;
		padding: 14px;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--line);
	}
	.question {
		margin: 0;
		font: var(--t-question);
		color: var(--text);
	}
	.answer {
		margin: 0.25rem 0 0;
		font: var(--t-body);
		color: var(--muted);
	}
	.body {
		margin-top: 12px;
		min-width: 0;
	}
</style>
