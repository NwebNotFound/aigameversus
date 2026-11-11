<script lang="ts">
	import type { CatalogModel } from '#lib/api.js';
	import { filterCatalog, NO_FILTER, PRICE_STEPS, priceLabel } from '#lib/catalog.js';
	import { BOT } from '#lib/new-match.js';

	/**
	 * Who takes one seat: a random bot or a model of the catalog. The choice goes
	 * into a hidden `seat` field, so the form works as before; the panel searches
	 * and filters the catalog.
	 */
	let {
		seat,
		value = $bindable(),
		models,
		enabled,
		favourites,
		ontogglefavourite
	}: {
		seat: string;
		value?: string;
		models: CatalogModel[];
		/** Whether this server seats models; otherwise only the bot can be chosen. */
		enabled: boolean;
		favourites: Set<string>;
		ontogglefavourite: (id: string) => void;
	} = $props();

	let open = $state(false);
	let query = $state('');
	let maxOutputUsd = $state<number | null>(null);
	let reasoning = $state(false);
	let verifiedOnly = $state(false);
	let onlyFavourites = $state(false);

	const chosen = $derived(models.find((m) => m.id === value) ?? null);
	const matching = $derived(
		filterCatalog(models, {
			...NO_FILTER,
			query,
			maxOutputUsd,
			reasoning,
			verifiedOnly,
			only: onlyFavourites ? favourites : null
		})
	);
	// A long list is cut: the search narrows it.
	const shown = $derived(matching.slice(0, 60));
	const total = $derived(matching.length);

	function choose(id: string) {
		value = id;
		open = false;
	}
</script>

<div class="picker" data-testid="picker-{seat}">
	<input type="hidden" name="seat" {value} />
	<button
		type="button"
		class="current"
		class:model={chosen !== null}
		aria-expanded={open}
		aria-label="Player of {seat}"
		data-value={value}
		onclick={() => (open = !open)}
	>
		{#if chosen}
			<strong>{chosen.name}</strong>
			<small>{chosen.openrouter_id} · {priceLabel(chosen)} per 1M</small>
			{#if !chosen.verified}<span class="tag warn">unverified</span>{/if}
			{#if chosen.high_price}<span class="tag danger">high price</span>{/if}
		{:else}
			<strong>Random bot</strong>
			<small>free</small>
		{/if}
	</button>

	{#if open}
		<div class="panel" role="dialog" aria-label="Choose the player of {seat}">
			<button type="button" class="bot" onclick={() => choose(BOT)}>Random bot (free)</button>
			{#if !enabled}
				<p class="muted">
					This server plays random bots only; models are listed but cannot be chosen.
				</p>
			{/if}
			<label class="search">
				<span class="sr-only">Search models for {seat}</span>
				<input
					type="search"
					placeholder="Search by name or vendor"
					bind:value={query}
					aria-label="Search models for {seat}"
				/>
			</label>
			<div class="filters">
				<select bind:value={maxOutputUsd} aria-label="Price of {seat}">
					{#each PRICE_STEPS as step (step.label)}
						<option value={step.usd}>{step.label}</option>
					{/each}
				</select>
				<label><input type="checkbox" bind:checked={reasoning} /> Reasoning</label>
				<label><input type="checkbox" bind:checked={verifiedOnly} /> Verified</label>
				<label><input type="checkbox" bind:checked={onlyFavourites} /> Favourites</label>
			</div>
			<p class="muted count" data-testid="picker-count">
				{total}
				{total === 1 ? 'model' : 'models'}{total > shown.length ? `, first ${shown.length}` : ''}
			</p>
			<ul class="list">
				{#each shown as model (model.id)}
					<li class:selected={model.id === value} data-id={model.id}>
						<button
							type="button"
							class="option"
							disabled={!enabled}
							onclick={() => choose(model.id)}
						>
							<strong>{model.name}</strong>
							<small>
								{model.openrouter_id} · {priceLabel(model)} per 1M{model.context_length
									? ` · ${Math.round(model.context_length / 1000)}k context`
									: ''}
							</small>
							<span class="tags">
								{#if model.verified}<span class="tag ok">verified</span>
								{:else}<span class="tag warn">unverified</span>{/if}
								{#if model.reasoning}<span class="tag">reasoning</span>{/if}
								{#if model.free}<span class="tag">free</span>{/if}
								{#if model.high_price}<span class="tag danger">high price</span>{/if}
							</span>
						</button>
						<button
							type="button"
							class="star"
							aria-pressed={favourites.has(model.id)}
							aria-label="{favourites.has(model.id) ? 'Unmark' : 'Mark'} {model.name} as favourite"
							onclick={() => ontogglefavourite(model.id)}
							>{favourites.has(model.id) ? '★' : '☆'}</button
						>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</div>

<style>
	.picker {
		position: relative;
		flex: 1 1 16rem;
		min-width: 0;
	}

	button,
	input,
	select {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
	}

	.current {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.1rem 0.5rem;
		width: 100%;
		padding: 0.4rem 0.7rem;
		text-align: left;
		cursor: pointer;
	}

	.current.model {
		border-color: var(--accent);
	}

	small,
	.muted {
		color: var(--muted);
	}

	.panel {
		display: grid;
		gap: 0.5rem;
		margin-top: 0.35rem;
		padding: 0.6rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
	}

	.bot,
	.search input {
		width: 100%;
		padding: 0.4rem 0.6rem;
		text-align: left;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.8rem;
		font-size: 0.9rem;
	}

	.filters select {
		padding: 0.25rem 0.4rem;
	}

	.count {
		margin: 0;
		font-size: 0.8rem;
	}

	.list {
		display: grid;
		gap: 0.3rem;
		max-height: 20rem;
		overflow-y: auto;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.list li {
		display: flex;
		gap: 0.3rem;
	}

	.option {
		display: grid;
		gap: 0.1rem;
		flex: 1;
		min-width: 0;
		padding: 0.4rem 0.6rem;
		text-align: left;
		cursor: pointer;
		overflow-wrap: anywhere;
	}

	.option:disabled {
		cursor: not-allowed;
		opacity: 0.6;
	}

	li.selected .option {
		border-color: var(--accent);
	}

	.star {
		padding: 0 0.6rem;
		cursor: pointer;
		color: var(--accent);
	}

	.tags {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.tag {
		font-size: 0.7rem;
		padding: 0 0.4rem;
		border-radius: 999px;
		border: 1px solid var(--border);
		color: var(--muted);
	}

	.tag.ok {
		color: #7ad69a;
		border-color: #7ad69a;
	}

	.tag.warn {
		color: var(--accent);
		border-color: var(--accent);
	}

	.tag.danger {
		color: var(--danger);
		border-color: var(--danger);
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
</style>
