<script lang="ts" generics="T extends string">
	/** Underline tabs: Watch, Report, Thoughts, Raw log. */
	let {
		tabs,
		value = $bindable(),
		label,
		onchange
	}: {
		tabs: { value: T; label: string; testid?: string }[];
		value: T;
		label: string;
		onchange?: (value: T) => void;
	} = $props();
</script>

<div class="tabs" role="tablist" aria-label={label}>
	{#each tabs as tab (tab.value)}
		<button
			type="button"
			role="tab"
			aria-selected={value === tab.value}
			data-testid={tab.testid}
			onclick={() => {
				value = tab.value;
				onchange?.(tab.value);
			}}>{tab.label}</button
		>
	{/each}
</div>

<style>
	.tabs {
		display: inline-flex;
		gap: 0.25rem;
	}
	button {
		font: var(--t-body);
		color: var(--muted);
		background: none;
		border: 0;
		border-bottom: 2px solid transparent;
		padding: 0.3rem 0.5rem;
		cursor: pointer;
		transition:
			color var(--ease),
			border-color var(--ease);
	}
	button[aria-selected='true'] {
		color: var(--text);
		border-bottom-color: var(--brand);
	}
</style>
