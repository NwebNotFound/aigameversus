<script lang="ts">
	import type { MatchEvent } from '#lib/api.js';
	import {
		circlePoint,
		currentVotes,
		isWolf,
		roleName,
		tally,
		themeOf
	} from '#lib/boards/werewolfCircle.js';
	import { hidden } from '#lib/live.js';

	/**
	 * The Werewolf circle: every player on a ring with an avatar, dead players greyed out,
	 * roles only with spoilers on, a night or day backdrop and an arrow for each vote of the
	 * day. `events` is the match log so far, which is where the votes come from.
	 */
	let {
		spec,
		spoilers,
		events = []
	}: { spec: Record<string, unknown>; spoilers: boolean; events?: MatchEvent[] } = $props();

	interface Seat {
		player: string;
		role: string | null;
		alive: boolean;
	}

	const seats = $derived(spec.seats as Seat[]);
	const theme = $derived(themeOf(spec.phase));
	const hideRoles = $derived(hidden('role', spoilers));
	const votes = $derived(currentVotes(events));
	const counts = $derived(tally(votes));
	const points = $derived(
		Object.fromEntries(seats.map((s, i) => [s.player, circlePoint(i, seats.length)]))
	);
	const heading = $derived(
		spec.phase === 'night'
			? `Night ${spec.night}`
			: spec.phase === 'over'
				? 'Game over'
				: `Day ${spec.day || spec.night}`
	);

	/** An arrow from one seat to another, stopping short of both avatars. */
	function arrow(from: string, to: string) {
		const a = points[from];
		const b = points[to];
		if (!a || !b || from === to) return null;
		const dx = b.left - a.left;
		const dy = b.top - a.top;
		const length = Math.hypot(dx, dy) || 1;
		const start = 6 / length;
		const end = 1 - 8 / length;
		return {
			x1: a.left + dx * start,
			y1: a.top + dy * start,
			x2: a.left + dx * end,
			y2: a.top + dy * end
		};
	}

	const palette = ['#f0b35a', '#7fb8ff', '#7ad69a', '#ff7a7a', '#c9a0ff', '#ffd27f'];
	const colour = (index: number) => palette[index % palette.length];
</script>

<div class="circle {theme}" data-testid="board" data-layout="player_circle" data-theme={theme}>
	<div class="sky" aria-hidden="true">
		{#if theme === 'night'}
			<svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice">
				<circle cx="92" cy="8" r="5" fill="#e8e4d0" />
				<circle cx="94" cy="7" r="4.3" fill="#0e1430" />
				{#each [[12, 14], [30, 8], [55, 10], [70, 22], [20, 40], [90, 50], [8, 70], [40, 90], [75, 88]] as [x, y] (`${x}/${y}`)}
					<circle cx={x} cy={y} r="0.7" fill="#fff" />
				{/each}
			</svg>
		{:else}
			<svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid slice">
				<circle cx="92" cy="8" r="5.5" fill={theme === 'dusk' ? '#ff9a5a' : '#ffd27f'} />
			</svg>
		{/if}
	</div>

	<div class="phase" data-testid="phase">{heading}</div>

	<svg class="arrows" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
		<defs>
			<marker
				id="vote-head"
				viewBox="0 0 6 6"
				refX="5"
				refY="3"
				markerWidth="4"
				markerHeight="4"
				orient="auto"
			>
				<path d="M0 0 L6 3 L0 6 z" fill="#ffb347" />
			</marker>
		</defs>
		{#each votes as vote (vote.from)}
			{@const line = arrow(vote.from, vote.to)}
			{#if line}
				<line
					{...line}
					stroke="#ffb347"
					stroke-width="0.7"
					marker-end="url(#vote-head)"
					data-testid="vote-arrow"
				/>
			{/if}
		{/each}
	</svg>

	{#each seats as seat, index (seat.player)}
		{@const point = points[seat.player]}
		<section
			class="seat"
			class:dead={!seat.alive}
			class:turn={seat.player === spec.turn}
			style="left: {point.left}%; top: {point.top}%"
			data-testid="seat"
			aria-label={seat.player}
		>
			<svg class="avatar" viewBox="0 0 40 40" aria-hidden="true">
				<circle
					cx="20"
					cy="20"
					r="19"
					fill="var(--surface-raised)"
					stroke={colour(index)}
					stroke-width="2"
				/>
				<text x="20" y="26" text-anchor="middle" font-size="18" fill={colour(index)}>
					{seat.player.slice(-1).toUpperCase()}
				</text>
				{#if !seat.alive}
					<path d="M10 10 L30 30 M30 10 L10 30" stroke="var(--danger)" stroke-width="2.5" />
				{/if}
			</svg>
			<span class="name">{seat.player}</span>
			{#if hideRoles}
				<span class="role" data-testid="secret">?</span>
			{:else}
				<span class="role" class:wolf={isWolf(seat.role)} data-testid="role"
					>{roleName(seat.role)}</span
				>
			{/if}
			{#if !seat.alive}<span class="tag">dead</span>{/if}
			{#if counts[seat.player]}
				<span
					class="votes"
					data-testid="vote-count"
					aria-label="{counts[seat.player]} votes against"
				>
					{counts[seat.player]}
				</span>
			{/if}
		</section>
	{/each}
</div>

<style>
	.circle {
		position: relative;
		width: 100%;
		aspect-ratio: 1 / 1;
		min-height: 22rem;
		border-radius: var(--radius);
		overflow: hidden;
		border: 1px solid var(--border);
		transition: background 0.6s;
	}

	.circle.night {
		background: radial-gradient(circle at 50% 50%, #1a2147 0%, #0b0f26 80%);
	}

	.circle.dusk {
		background: radial-gradient(circle at 50% 50%, #4a2f4f 0%, #1c1428 80%);
	}

	.circle.day {
		background: radial-gradient(circle at 50% 50%, #3a4a36 0%, #1d281b 80%);
	}

	.sky,
	.arrows {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
	}

	.sky svg {
		width: 100%;
		height: 100%;
	}

	.phase {
		position: absolute;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		font-size: clamp(1rem, 4vw, 1.5rem);
		font-weight: 700;
		color: var(--text);
		opacity: 0.85;
		text-align: center;
	}

	.seat {
		position: absolute;
		transform: translate(-50%, -50%);
		z-index: 2;
		display: grid;
		justify-items: center;
		gap: 0.1rem;
		width: 4.2rem;
		text-align: center;
	}

	.avatar {
		width: 2.2rem;
		height: 2.2rem;
	}

	.name {
		font-size: 0.75rem;
		font-weight: 600;
	}

	.role {
		font-size: 0.65rem;
		padding: 0 0.35rem;
		border-radius: 999px;
		background: #0008;
		color: var(--accent-2);
	}

	.role.wolf {
		color: var(--danger);
	}

	.tag {
		font-size: 0.6rem;
		color: var(--muted);
	}

	.seat.dead {
		opacity: 0.45;
		filter: grayscale(1);
	}

	.seat.turn .avatar {
		filter: drop-shadow(0 0 4px var(--accent));
	}

	.votes {
		position: absolute;
		top: -0.2rem;
		right: 0.4rem;
		min-width: 1.1rem;
		height: 1.1rem;
		display: grid;
		place-items: center;
		border-radius: 999px;
		background: #ffb347;
		color: #1a1408;
		font-size: 0.7rem;
		font-weight: 700;
	}

	@media (max-width: 30rem) {
		.circle {
			min-height: 20rem;
		}
		.seat {
			width: 3.2rem;
		}
		.avatar {
			width: 1.7rem;
			height: 1.7rem;
		}
		.name,
		.role {
			font-size: 0.6rem;
		}
	}
</style>
