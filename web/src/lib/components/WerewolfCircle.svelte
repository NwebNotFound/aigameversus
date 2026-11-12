<script lang="ts">
	import type { MatchEvent, Seat as Player, TranscriptLine } from '#lib/api.js';
	import {
		causeWords,
		circlePoint,
		currentVotes,
		deathsOf,
		isWolf,
		onStage,
		ranking,
		roleName,
		tally,
		themeOf
	} from '#lib/boards/werewolfCircle.js';
	import Avatar from '#lib/components/Avatar.svelte';
	import RichText from '#lib/components/RichText.svelte';
	import SeatTag from '#lib/components/SeatTag.svelte';
	import { hidden } from '#lib/live.js';
	import { words } from '#lib/viewer.js';

	/**
	 * The Werewolf circle: every player on a ring with an avatar, dead players greyed out,
	 * roles only with spoilers on, a night or day backdrop and an arrow for each vote of the
	 * day. `events` is the match log so far, which is where the votes come from. The newest
	 * speech of the scene stands in the middle, its tail pointing at the speaker; a death
	 * turns the seat's card over to the role the game announced (public, so in every view).
	 */
	let {
		spec,
		spoilers,
		events = [],
		names = {},
		colours = {},
		subs = {},
		lines = [],
		players
	}: {
		spec: Record<string, unknown>;
		spoilers: boolean;
		events?: MatchEvent[];
		/** The transcript so far: the words on stage come from its speech lines. */
		lines?: TranscriptLine[];
		players?: Record<string, Player>;
		names?: Record<string, string>;
		colours?: Record<string, string>;
		subs?: Record<string, string | null>;
	} = $props();
	const label = (seat: string) => names[seat] ?? seat;
	/** On the ring the model stands on the line under the name, so "Tamsin (qwen-flash)" is "Tamsin". */
	const short = (seat: string) => label(seat).replace(/\s*\([^)]*\)$/, '') || label(seat);

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
	const deaths = $derived(deathsOf(events));
	const newest = $derived(Math.max(0, ...Object.values(deaths).map((d) => d.order)));
	const speech = $derived(onStage(lines));
	const speaker = $derived(speech?.actor ?? null);
	const standings = $derived(
		ranking(
			votes,
			seats.map((s) => s.player)
		)
	);
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

	<div class="phase" class:corner={!!speech || standings.length > 0} data-testid="phase">
		{heading}
	</div>

	{#if speech || standings.length}
		<div class="centre">
			{#if speech && speaker}
				{#key speech}
					<figure
						class="speech"
						class:whisper={speech.kind === 'whisper'}
						data-testid="stage-speech"
						data-seat={speaker}
					>
						<figcaption>
							<Avatar name={label(speaker)} colourKey={colours[speaker] ?? speaker} size={20} />
							<strong>{short(speaker)}</strong>
							{#if speech.kind === 'whisper'}<span class="pack"
									>pack chat · only wolves hear it</span
								>{/if}
						</figcaption>
						<blockquote>
							<RichText text={words(speech) ?? speech.text} {players} />
						</blockquote>
					</figure>
				{/key}
			{/if}
			{#if standings.length}
				<ol class="tally" aria-label="Votes so far" data-testid="tally">
					{#each standings as row, i (row.player)}
						<li class:lead={i === 0 && row.votes > (standings[1]?.votes ?? 0)}>
							<Avatar
								name={label(row.player)}
								colourKey={colours[row.player] ?? row.player}
								size={16}
							/>
							<span class="who">{short(row.player)}</span>
							<b>{row.votes}</b>
						</li>
					{/each}
				</ol>
			{/if}
		</div>
	{/if}

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
		{#if speaker && points[speaker]}
			<line
				class="tail"
				class:whisper={speech?.kind === 'whisper'}
				x1="50"
				y1="50"
				x2={points[speaker].left}
				y2={points[speaker].top}
				data-testid="speech-tail"
			/>
		{/if}
		{#each votes as vote, order (vote.from)}
			{@const line = arrow(vote.from, vote.to)}
			{#if line}
				<line
					{...line}
					stroke="#ffb347"
					stroke-width="0.7"
					marker-end="url(#vote-head)"
					pathLength="100"
					style="--order: {order}"
					data-testid="vote-arrow"
				/>
			{/if}
		{/each}
	</svg>

	{#each seats as seat (seat.player)}
		{@const point = points[seat.player]}
		{@const death = seat.alive ? null : deaths[seat.player]}
		<section
			class="seat"
			class:dead={!seat.alive}
			class:turn={seat.player === spec.turn}
			class:speaking={seat.player === speaker}
			style="left: {point.left}%; top: {point.top}%"
			data-testid="seat"
			data-seat={seat.player}
			aria-label={label(seat.player)}
		>
			<span class="avatar">
				<Avatar
					name={label(seat.player)}
					colourKey={colours[seat.player] ?? seat.player}
					size={34}
					active={seat.player === spec.turn}
					out={!seat.alive}
				/>
				{#if !seat.alive}
					<svg class="grave" viewBox="0 0 12 12" aria-hidden="true"
						><path d="M3 3 L9 9 M9 3 L3 9" /></svg
					>
				{/if}
			</span>
			<SeatTag seat={seat.player} name={short(seat.player)} sub={subs[seat.player]} compact />
			{#if !hideRoles}
				<span
					class="role"
					class:wolf={isWolf(seat.role)}
					class:fresh={!!death && death.order === newest}
					data-testid="role">{roleName(seat.role)}</span
				>
			{:else if death?.role}
				<span
					class="role"
					class:wolf={isWolf(death.role)}
					class:fresh={death.order === newest}
					data-testid="revealed">{roleName(death.role)}</span
				>
			{:else}
				<span class="role" data-testid="secret">?</span>
			{/if}
			{#if !seat.alive}<span class="tag" data-testid="death"
					>{death ? causeWords(death.cause) : 'dead'}</span
				>{/if}
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

	.circle {
		container-type: inline-size;
	}

	.phase {
		position: absolute;
		z-index: 1;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		font-size: clamp(1rem, 4vw, 1.5rem);
		font-weight: 700;
		color: var(--text);
		opacity: 0.85;
		text-align: center;
		white-space: nowrap;
		transition:
			top 300ms ease,
			font-size 300ms ease;
	}

	/* While someone speaks or votes are cast, the phase moves to the corner; the middle is the stage. */
	.phase.corner {
		left: 0.8rem;
		top: 0.7rem;
		transform: none;
		padding: 0.15rem 0.55rem;
		border-radius: 999px;
		background: #0007;
		font-size: 0.75rem;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		opacity: 0.7;
	}

	.centre {
		position: absolute;
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		z-index: 3;
		width: min(50%, 22rem);
		display: grid;
		gap: 0.45rem;
		justify-items: center;
	}

	.speech {
		margin: 0;
		width: 100%;
		padding: 0.55rem 0.75rem 0.6rem;
		border-radius: 14px;
		background: color-mix(in srgb, var(--surface) 90%, transparent);
		border: 1px solid color-mix(in srgb, var(--accent) 45%, var(--border));
		box-shadow: 0 8px 28px #0008;
		animation: rise 260ms ease-out both;
	}

	.speech.whisper {
		border-color: color-mix(in srgb, var(--danger) 60%, var(--border));
		background: color-mix(in srgb, #2a0f14 88%, transparent);
	}

	.speech figcaption {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.35rem;
		margin-bottom: 0.3rem;
		font-size: 0.75rem;
		color: var(--muted);
	}

	.speech figcaption strong {
		color: var(--text);
		font-weight: 650;
	}

	.pack {
		color: var(--danger);
	}

	.speech blockquote {
		margin: 0;
		font-size: 0.85rem;
		line-height: 1.4;
		/* Five lines on stage, fading out; the commentary has the whole speech. */
		max-height: 7em;
		overflow: hidden;
		mask-image: linear-gradient(to bottom, #000 calc(100% - 1.6em), transparent);
	}

	@keyframes rise {
		from {
			opacity: 0;
			transform: translateY(6px) scale(0.98);
		}
	}

	.tally {
		display: flex;
		flex-wrap: wrap;
		justify-content: center;
		gap: 0.3rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.tally li {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
		padding: 0.1rem 0.5rem 0.1rem 0.15rem;
		border-radius: 999px;
		background: #000b;
		border: 1px solid #ffb34755;
		font-size: 0.75rem;
	}

	.tally li.lead {
		border-color: #ffb347;
		box-shadow: 0 0 12px #ffb34755;
	}

	.tally .who {
		max-width: 6.5rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.tally b {
		color: #ffb347;
		font-variant-numeric: tabular-nums;
	}

	.tail {
		stroke: color-mix(in srgb, var(--accent) 75%, transparent);
		stroke-width: 0.4;
		stroke-dasharray: 1.2 1;
	}

	.tail.whisper {
		stroke: var(--danger);
	}

	.seat.speaking .avatar {
		border-radius: 50%;
		box-shadow:
			0 0 0 2px var(--accent),
			0 0 18px color-mix(in srgb, var(--accent) 70%, transparent);
	}

	/* The card of the newest death turns over to the role. */
	.role.fresh {
		animation: turn 600ms ease-out both;
	}

	@keyframes turn {
		from {
			transform: rotateY(90deg);
			opacity: 0;
		}
	}

	/* A small circle (phones): the model line under each name gives way to the stage. */
	@container (max-width: 30rem) {
		.seat :global(.sub) {
			display: none;
		}
		.centre {
			width: 56%;
		}
		.speech {
			padding: 0.4rem 0.55rem;
		}
		.speech blockquote {
			font-size: 0.75rem;
			max-height: 5.6em;
		}
		.tally .who {
			max-width: 4.5rem;
		}
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
		position: relative;
		display: inline-block;
	}

	.grave {
		position: absolute;
		right: -0.2rem;
		bottom: -0.1rem;
		width: 0.95rem;
		height: 0.95rem;
		border-radius: 50%;
		background: var(--bg);
		fill: none;
		stroke: var(--danger);
		stroke-width: 1.8;
		stroke-linecap: round;
	}

	/* The votes draw one after another, so the tally builds up as it happened. */
	line[data-testid='vote-arrow'] {
		stroke-dasharray: 100;
		animation: draw 450ms ease-out both;
		animation-delay: calc(var(--order) * 120ms);
	}

	@keyframes draw {
		from {
			stroke-dashoffset: 100;
		}
		to {
			stroke-dashoffset: 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		line[data-testid='vote-arrow'],
		.speech,
		.role.fresh {
			animation: none;
		}

		.circle,
		.phase {
			transition: none;
		}
	}

	.name {
		font-size: 0.75rem;
		font-weight: 600;
	}

	.role {
		font-size: 0.75rem;
		padding: 0 0.35rem;
		border-radius: 999px;
		background: #0008;
		color: var(--accent-2);
	}

	.role.wolf {
		color: var(--danger);
	}

	.tag {
		font-size: 0.75rem;
		color: var(--muted);
	}

	.seat.dead {
		opacity: 0.45;
		filter: grayscale(1);
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
		.name,
		.role {
			font-size: 0.7rem;
		}
	}
</style>
