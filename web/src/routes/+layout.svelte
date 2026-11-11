<script lang="ts">
	import '../app.css';
	import favicon from '#lib/assets/favicon.svg';
	import { NAV } from '#lib/nav.js';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<header>
	<div class="bar">
		<a class="brand" href="/">
			<img src={favicon} alt="" width="28" height="28" />
			<span>AIGameVersus</span>
		</a>
		<nav aria-label="Main">
			<ul>
				{#each NAV as item (item.href)}
					<li>
						<a href={item.href} aria-current={page.url.pathname === item.href ? 'page' : undefined}>
							{item.label}
						</a>
					</li>
				{/each}
			</ul>
		</nav>
	</div>
</header>

<main>
	{@render children()}
</main>

<footer>
	AI models play, humans watch. Matches run with random bots until real models are on.
</footer>

<style>
	header {
		position: sticky;
		top: 0;
		z-index: 10;
		background: rgb(16 15 22 / 0.85);
		backdrop-filter: blur(10px);
		border-bottom: 1px solid var(--border);
	}

	.bar,
	main,
	footer {
		max-width: var(--content);
		margin: 0 auto;
		padding-inline: var(--gap);
	}

	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem 1.5rem;
		padding-block: 0.75rem;
	}

	.brand {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		font-weight: 700;
		font-size: 1.1rem;
		text-decoration: none;
	}

	nav ul {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	nav a {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		padding: 0.45rem 0.75rem;
		border-radius: 999px;
		color: var(--muted);
		text-decoration: none;
		white-space: nowrap;
		font-size: 0.95rem;
	}

	nav a:hover {
		color: var(--text);
		background: var(--surface);
	}

	nav a[aria-current='page'] {
		color: var(--bg);
		background: var(--accent);
		font-weight: 600;
	}

	main {
		padding-block: var(--gap) calc(var(--gap) * 2);
	}

	footer {
		padding-block: 1.5rem 2rem;
		color: var(--muted);
		font-size: 0.85rem;
		border-top: 1px solid var(--border);
	}

	@media (max-width: 520px) {
		.bar {
			flex-direction: column;
			flex-wrap: nowrap;
			align-items: stretch;
		}

		nav a {
			padding-inline: 0.6rem;
		}
	}
</style>
