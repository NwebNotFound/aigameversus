<script lang="ts">
	import {
		MAX_STRATEGY,
		OPTIONS,
		OUTPUT_RANGE,
		PRESETS,
		TEMPERATURE_RANGE,
		configOf,
		isDefault,
		presetOf,
		problem,
		summary,
		type SeatConfig
	} from '#lib/seat-config.js';

	interface Props {
		seat: string;
		config: SeatConfig;
		/** The game: options for other games are not shown. */
		game: string;
		/** The option keys the arena takes per seat (`GET /setup`); the rest are shown off. */
		supported: readonly string[];
		/** The other seats this one may copy from. */
		others: string[];
		oncopy: (from: string) => void;
		onapplyall: () => void;
	}

	let { seat, config = $bindable(), game, supported, others, oncopy, onapplyall }: Props = $props();

	const shown = $derived(OPTIONS.filter((o) => !o.games || o.games.includes(game)));
	const live = $derived(shown.some((o) => supported.includes(o.key)));
	const preset = $derived(presetOf(config));
	const issue = $derived(problem(config));
	const outputMode = $derived(
		typeof config.max_output_tokens === 'number' ? 'custom' : config.max_output_tokens
	);

	function set<K extends keyof SeatConfig>(key: K, value: SeatConfig[K]) {
		config = { ...config, [key]: value };
	}

	function setOutput(mode: string) {
		if (mode === 'custom') set('max_output_tokens', 1000);
		else set('max_output_tokens', mode as 'default' | 'adaptive');
	}
</script>

<details class="configure" data-testid="configure-{seat}">
	<summary>
		<span>Configure</span>
		<span class="badge" class:changed={summary(config) !== 'Default'} data-testid="summary-{seat}"
			>{summary(config)}</span
		>
	</summary>

	<div class="panel">
		{#if !live}
			<p class="hint" data-testid="not-live-{seat}">
				Not possible yet: the live arena does not take options per seat. You can prepare them; the
				match starts with the defaults.
			</p>
		{/if}

		<div class="presets" role="group" aria-label="Presets for {seat}">
			{#each PRESETS as option (option.id)}
				<button
					type="button"
					class:active={preset?.id === option.id}
					aria-pressed={preset?.id === option.id}
					title={option.help}
					onclick={() => (config = configOf(option.id))}>{option.label}</button
				>
			{/each}
			<button type="button" onclick={() => (config = configOf())}>Reset</button>
		</div>
		{#if preset}<p class="hint">{preset.help}</p>{/if}

		{#each shown as option (option.key)}
			{@const off = !supported.includes(option.key)}
			{@const id = `${seat}-${option.key}`}
			<div class="option" class:off data-testid="option-{seat}-{option.key}">
				<label for={id}>
					{option.label}
					{#if !isDefault(config, option.key)}<span class="dot" aria-label="changed">•</span>{/if}
				</label>
				{#if option.key === 'max_output_tokens'}
					<div class="pair">
						<select {id} value={outputMode} onchange={(e) => setOutput(e.currentTarget.value)}>
							{#each option.choices ?? [] as choice (choice.value)}
								<option value={choice.value}>{choice.label}</option>
							{/each}
						</select>
						{#if typeof config.max_output_tokens === 'number'}
							<input
								type="number"
								aria-label="Tokens per answer for {seat}"
								min={OUTPUT_RANGE.min}
								max={OUTPUT_RANGE.max}
								step="1"
								value={config.max_output_tokens}
								oninput={(e) => set('max_output_tokens', Number(e.currentTarget.value))}
							/>
						{/if}
					</div>
				{:else if option.key === 'temperature'}
					<input
						{id}
						type="number"
						min={TEMPERATURE_RANGE.min}
						max={TEMPERATURE_RANGE.max}
						step={TEMPERATURE_RANGE.step}
						placeholder="model default"
						value={config.temperature ?? ''}
						oninput={(e) =>
							set(
								'temperature',
								e.currentTarget.value === '' ? null : Number(e.currentTarget.value)
							)}
					/>
				{:else if option.key === 'strategy'}
					<textarea
						{id}
						rows="2"
						maxlength={MAX_STRATEGY}
						placeholder="none"
						value={config.strategy}
						oninput={(e) => set('strategy', e.currentTarget.value)}></textarea>
				{:else}
					<select
						{id}
						value={config[option.key]}
						onchange={(e) => set(option.key, e.currentTarget.value as never)}
					>
						{#each option.choices ?? [] as choice (choice.value)}
							<option value={choice.value}>{choice.label}</option>
						{/each}
					</select>
				{/if}
				<p class="hint">
					{option.help}{#if off}<em> Not taken by this arena yet.</em>{/if}
				</p>
			</div>
		{/each}

		{#if issue}<p class="field-error" role="alert" data-testid="config-problem-{seat}">
				{issue}
			</p>{/if}

		<div class="actions" role="group" aria-label="Copy settings of {seat}">
			{#if others.length}
				<label>
					<span>Copy from</span>
					<select
						aria-label="Copy settings to {seat} from"
						value=""
						onchange={(e) => {
							if (e.currentTarget.value) oncopy(e.currentTarget.value);
							e.currentTarget.value = '';
						}}
					>
						<option value="">seat…</option>
						{#each others as other (other)}
							<option value={other}>{other}</option>
						{/each}
					</select>
				</label>
				<button type="button" onclick={onapplyall}>Apply to all seats</button>
			{/if}
		</div>
	</div>
</details>

<style>
	.configure {
		flex-basis: 100%;
		border: 1px solid var(--border);
		border-radius: var(--radius);
		background: var(--surface-raised);
	}

	summary {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.35rem 0.7rem;
		cursor: pointer;
		font-size: 0.9rem;
	}

	.badge {
		font-size: 0.8rem;
		color: var(--muted);
		border: 1px solid var(--border);
		border-radius: 999px;
		padding: 0 0.5rem;
	}

	.badge.changed {
		color: var(--text);
		border-color: var(--accent);
	}

	.panel {
		display: grid;
		gap: 0.6rem;
		padding: 0.25rem 0.7rem 0.7rem;
	}

	.presets,
	.actions,
	.pair {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
	}

	.presets button.active {
		border-color: var(--accent);
		font-weight: 600;
	}

	.option {
		display: grid;
		gap: 0.2rem;
		min-width: 0;
	}

	.option.off label {
		color: var(--muted);
	}

	.option label {
		font-weight: 600;
		font-size: 0.9rem;
	}

	.dot {
		color: var(--accent);
	}

	.hint {
		margin: 0;
		font-size: 0.85rem;
		color: var(--muted);
	}

	.field-error {
		margin: 0;
		font-size: 0.9rem;
		color: var(--danger);
	}

	input,
	select,
	textarea,
	button {
		font: inherit;
		color: var(--text);
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.3rem 0.6rem;
		min-height: 2.1rem;
		max-width: 100%;
		box-sizing: border-box;
	}

	textarea {
		width: 100%;
		resize: vertical;
	}

	button {
		cursor: pointer;
		font-size: 0.9rem;
	}

	.actions label {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.9rem;
	}
</style>
