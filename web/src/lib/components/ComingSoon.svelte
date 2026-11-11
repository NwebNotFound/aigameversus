<script lang="ts">
	let { title, text }: { title: string; text: string } = $props();
</script>

<svelte:head>
	<title>{title} · AIGameVersus</title>
</svelte:head>

<section>
	<h1>{title}</h1>
	<p class="badge">Coming soon</p>
	<p>{text}</p>
	<a href="/">Back to the games</a>
</section>

<style>
	section {
		max-width: 36rem;
		padding-block: clamp(1.5rem, 6vw, 4rem);
	}

	h1 {
		margin: 0;
		font-size: clamp(1.8rem, 6vw, 2.6rem);
	}

	.badge {
		display: inline-block;
		margin: 0.75rem 0 0;
		padding: 0.15rem 0.7rem;
		border-radius: 999px;
		background: var(--surface-raised);
		color: var(--accent);
		font-size: 0.85rem;
	}

	p {
		color: var(--muted);
	}

	a {
		color: var(--accent);
	}
</style>
