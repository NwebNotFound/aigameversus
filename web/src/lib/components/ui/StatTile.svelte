<script lang="ts">
	/** A number with its label; `of` turns it into "n / of", so a rate shows what it rests on. */
	let {
		value,
		label,
		of = null,
		tone = 'plain',
		testid
	}: {
		value: string | number;
		label: string;
		of?: number | null;
		tone?: 'plain' | 'danger' | 'ok' | 'warn';
		testid?: string;
	} = $props();
</script>

<div class="tile {tone}" data-testid={testid}>
	<b class="num"
		>{value}{#if of !== null}<small> / {of}</small>{/if}</b
	>
	<span>{label}</span>
</div>

<style>
	.tile {
		display: grid;
		gap: 0.15rem;
		min-width: 0;
		padding: 10px 12px;
		border-radius: var(--radius-row);
		background: var(--raised);
	}
	b {
		font-size: 1.25rem;
		font-weight: 650;
		line-height: 1.2;
	}
	small {
		font-size: 0.8rem;
		color: var(--muted);
		font-weight: 500;
	}
	span {
		font: var(--t-small);
		color: var(--muted);
	}
	.danger b {
		color: var(--danger);
	}
	.ok b {
		color: var(--ok);
	}
	.warn b {
		color: var(--brand);
	}
</style>
