<script lang="ts" generics="T extends string">
	/**
	 * Underline tabs: Watch, Report, Thoughts, Raw log. A WAI-ARIA tab list: only the
	 * selected tab is in the tab order, the arrow keys (and Home, End) move to and select
	 * the next tab, and `panel` names the element each tab controls.
	 */
	let {
		tabs,
		value = $bindable(),
		label,
		onchange
	}: {
		tabs: { value: T; label: string; testid?: string; panel?: string }[];
		value: T;
		label: string;
		onchange?: (value: T) => void;
	} = $props();

	let buttons = $state<HTMLButtonElement[]>([]);

	function pick(index: number) {
		const tab = tabs[(index + tabs.length) % tabs.length];
		value = tab.value;
		onchange?.(tab.value);
		buttons[tabs.indexOf(tab)]?.focus();
	}

	function onkeydown(event: KeyboardEvent, index: number) {
		const moves: Record<string, number> = {
			ArrowRight: index + 1,
			ArrowLeft: index - 1,
			Home: 0,
			End: tabs.length - 1
		};
		if (!(event.key in moves)) return;
		event.preventDefault();
		pick(moves[event.key]);
	}
</script>

<div class="tabs" role="tablist" aria-label={label}>
	{#each tabs as tab, index (tab.value)}
		<button
			bind:this={buttons[index]}
			type="button"
			role="tab"
			id="tab-{tab.value}"
			aria-selected={value === tab.value}
			aria-controls={tab.panel}
			tabindex={value === tab.value ? 0 : -1}
			data-testid={tab.testid}
			onclick={() => pick(index)}
			onkeydown={(event) => onkeydown(event, index)}>{tab.label}</button
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
