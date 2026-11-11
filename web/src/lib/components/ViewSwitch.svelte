<script lang="ts">
	import { page } from '$app/state';
	import type { View } from '#lib/viewer.js';

	/**
	 * Spectator view or spoiler-free. Each is its own page load, so a spoiler-free page
	 * never fetched the hidden data it does not show.
	 */
	let { view }: { view: View } = $props();

	function href(to: View) {
		const url = new URL(page.url.href);
		if (to === 'spectator') url.searchParams.delete('view');
		else url.searchParams.set('view', to);
		return url.pathname + url.search;
	}
</script>

<div class="switch" role="group" aria-label="What you see" data-testid="view-switch">
	<a
		href={href('spectator')}
		aria-current={view === 'spectator' ? 'true' : undefined}
		data-sveltekit-replacestate
		title="Thoughts, hands and roles: everything the players hide from each other"
	>
		<svg viewBox="0 0 16 16" aria-hidden="true"
			><path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8Z" /><circle
				cx="8"
				cy="8"
				r="2"
			/></svg
		>
		Spectator<span class="long"> view</span>
	</a>
	<a
		href={href('spoiler-free')}
		aria-current={view === 'spoiler-free' ? 'true' : undefined}
		data-sveltekit-replacestate
		title="Only what every player saw, so you can guess along"
	>
		<svg viewBox="0 0 16 16" aria-hidden="true"
			><path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8Z" /><path
				d="M2.5 13.5 13.5 2.5"
			/></svg
		>
		Spoiler-free
	</a>
</div>

<style>
	.switch {
		display: inline-flex;
		padding: 3px;
		gap: 2px;
		border-radius: 999px;
		background: var(--surface);
		border: 1px solid var(--border);
	}

	a {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		padding: 0.3rem 0.8rem;
		min-height: 2rem;
		border-radius: 999px;
		font-size: 0.875rem;
		text-decoration: none;
		color: var(--muted);
	}

	a[aria-current='true'] {
		color: var(--text);
		background: var(--surface-raised);
	}

	a:first-child[aria-current='true'] {
		color: var(--thought);
		box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--thought) 45%, transparent);
	}

	@media (max-width: 30rem) {
		.long {
			display: none;
		}
	}

	svg {
		width: 1rem;
		height: 1rem;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.5;
		stroke-linecap: round;
	}
</style>
