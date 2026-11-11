<script lang="ts">
	import {
		LANGS,
		STYLES,
		chroniclePath,
		explain,
		type Chronicle,
		type LangId,
		type StyleId
	} from '#lib/chronicle.js';

	/**
	 * The chronicle tab: the match told as a story, in a chosen style and language, with a
	 * Markdown download. It names hidden cards and roles, so the arena only tells it once
	 * the match has finished; for a running match the panel says so instead.
	 */
	let { id }: { id: string } = $props();

	let style = $state<StyleId>('epic');
	let lang = $state<LangId>('en');

	type Load =
		| { state: 'loading' }
		| { state: 'ok'; chronicle: Chronicle }
		| { state: 'failed'; status: number };
	let load = $state<Load>({ state: 'loading' });

	// Fetch again whenever the style or the language changes; an older answer never wins.
	$effect(() => {
		const url = chroniclePath(id, style, lang);
		const controller = new AbortController();
		load = { state: 'loading' };
		fetch(url, { signal: controller.signal })
			.then(async (response) => {
				load = response.ok
					? { state: 'ok', chronicle: await response.json() }
					: { state: 'failed', status: response.status };
			})
			.catch((error) => {
				if (error?.name !== 'AbortError') load = { state: 'failed', status: 502 };
			});
		return () => controller.abort();
	});

	const download = $derived(chroniclePath(id, style, lang, 'markdown'));
</script>

<section class="chronicle" aria-label="Chronicle" data-testid="chronicle">
	<div class="bar">
		<label>
			Style
			<select bind:value={style} data-testid="chronicle-style">
				{#each STYLES as option (option.id)}
					<option value={option.id}>{option.label}</option>
				{/each}
			</select>
		</label>
		<label>
			Language
			<select bind:value={lang} data-testid="chronicle-lang">
				{#each LANGS as option (option.id)}
					<option value={option.id}>{option.label}</option>
				{/each}
			</select>
		</label>
		{#if load.state === 'ok'}
			<a class="button" href={download} download data-testid="chronicle-download"> Download .md </a>
		{/if}
	</div>

	{#if load.state === 'loading'}
		<p class="muted" role="status" data-testid="chronicle-loading">Telling the story…</p>
	{:else if load.state === 'failed'}
		<div class="notice" role="status" data-testid="chronicle-problem" data-status={load.status}>
			<strong>No chronicle</strong>
			<span>{explain(load.status)}</span>
		</div>
	{:else if load.chronicle.chapters.length === 0}
		<div class="notice" role="status" data-testid="chronicle-empty">
			<strong>Nothing to tell</strong>
			<span>This match has no chapters.</span>
		</div>
	{:else}
		<article lang={load.chronicle.lang} data-testid="chronicle-story">
			<h2>{load.chronicle.title}</h2>
			{#each load.chronicle.chapters as chapter (chapter.number)}
				<h3 data-testid="chronicle-chapter">{chapter.title}</h3>
				<p>{chapter.text}</p>
			{/each}
		</article>
	{/if}
</section>

<style>
	.chronicle {
		display: grid;
		gap: 1rem;
		padding-block: 0.5rem 2rem;
	}

	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem 1.25rem;
	}

	label {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}

	select,
	.button {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.35rem 0.8rem;
		min-height: 2.25rem;
		text-decoration: none;
	}

	.button {
		cursor: pointer;
	}

	.muted {
		margin: 0;
		color: var(--muted);
	}

	.notice {
		display: grid;
		gap: 0.25rem;
		padding: 1rem 1.25rem;
		border-radius: var(--radius);
		border: 1px dashed var(--border);
		background: var(--surface);
	}

	article {
		display: grid;
		gap: 0.6rem;
		max-width: 46rem;
		line-height: 1.6;
		overflow-wrap: anywhere;
	}

	h2 {
		margin: 0.25rem 0 0;
		font-size: clamp(1.3rem, 4vw, 1.8rem);
	}

	h3 {
		margin: 0.75rem 0 0;
		font-size: 1.1rem;
		color: var(--accent);
	}

	p {
		margin: 0;
	}
</style>
