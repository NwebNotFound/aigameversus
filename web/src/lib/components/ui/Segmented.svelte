<script lang="ts" generics="T extends string">
	/** Two to five options in one control (a radio group). */
	let {
		options,
		value = $bindable(),
		label,
		onchange
	}: {
		options: { value: T; label: string }[];
		value: T;
		label: string;
		onchange?: (value: T) => void;
	} = $props();
</script>

<div class="segmented" role="radiogroup" aria-label={label}>
	{#each options as option (option.value)}
		<button
			type="button"
			role="radio"
			aria-checked={value === option.value}
			onclick={() => {
				value = option.value;
				onchange?.(option.value);
			}}>{option.label}</button
		>
	{/each}
</div>

<style>
	.segmented {
		display: inline-flex;
		padding: 2px;
		gap: 2px;
		border-radius: var(--radius-control);
		background: var(--sunken);
		border: 1px solid var(--line);
	}
	button {
		font: var(--t-small);
		color: var(--muted);
		background: none;
		border: 0;
		border-radius: 4px;
		padding: 0.25rem 0.65rem;
		cursor: pointer;
		transition:
			background var(--ease),
			color var(--ease);
	}
	button[aria-checked='true'] {
		color: var(--text);
		background: var(--raised);
	}
</style>
