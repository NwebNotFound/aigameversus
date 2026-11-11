<script lang="ts">
	import { enhance } from '$app/forms';
	import WerewolfRoles from '#lib/components/WerewolfRoles.svelte';
	import { gameName } from '#lib/games.js';
	import { SPEEDS } from '#lib/live.js';
	import {
		BOT,
		DEFAULT_TEMPLATE,
		DEFAULT_TURN_DELAY,
		GAMES_WITH_LANGUAGE,
		LANGUAGES
	} from '#lib/new-match.js';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const games = $derived(data.games.state === 'ok' ? data.games.data : []);
	const setup = $derived(data.setup.state === 'ok' ? data.setup.data : null);
	const errors = $derived<Record<string, string | undefined>>(form?.errors ?? {});

	// What was entered before a refused submit, else the defaults.
	// svelte-ignore state_referenced_locally
	let gameId = $state(form?.values?.game || 'liars_deck');
	const game = $derived(games.find((g) => g.id === gameId) ?? games[0]);
	// svelte-ignore state_referenced_locally
	let players = $state(Number(form?.values?.players) || 0);
	const seatCount = $derived(
		game ? Math.min(Math.max(players || game.min_players, game.min_players), game.max_players) : 0
	);
	let submitting = $state(false);

	const werewolfRoles = $derived(data.werewolfRoles.state === 'ok' ? data.werewolfRoles.data : []);
	// The role counts entered before a refused submit.
	const enteredCounts = $derived(
		Object.fromEntries(
			Object.entries(form?.values ?? {})
				.filter(([name]) => name.startsWith('role_'))
				.map(([name, value]) => [name.slice('role_'.length), Number(value) || 0])
		)
	);

	function chooseGame(id: string) {
		gameId = id;
		players = 0; // the new game's minimum
	}
</script>

<svelte:head>
	<title>New match · AIGameVersus</title>
</svelte:head>

<h1>New match</h1>

{#if data.games.state !== 'ok' || !game}
	<div class="notice error" role="status" data-testid="arena-unreachable">
		<strong>Arena unreachable</strong>
		<span>
			The arena API did not answer ({data.games.state === 'unreachable'
				? data.games.reason
				: 'no games'}). Is the stack running?
		</span>
	</div>
{:else}
	<form
		method="POST"
		use:enhance={() => {
			submitting = true;
			return async ({ update }) => {
				await update({ reset: false });
				submitting = false;
			};
		}}
	>
		{#if errors.form}
			<p class="problem" role="alert" data-testid="form-error">{errors.form}</p>
		{/if}

		<fieldset>
			<legend>Game</legend>
			<div class="games">
				{#each games as option (option.id)}
					<label class="game" class:chosen={option.id === game.id}>
						<input
							type="radio"
							name="game"
							value={option.id}
							checked={option.id === game.id}
							onchange={() => chooseGame(option.id)}
						/>
						<strong>{gameName(option.id)}</strong>
						<small>{option.min_players}–{option.max_players} players</small>
					</label>
				{/each}
			</div>
			{#if errors.game}<p class="field-error">{errors.game}</p>{/if}
		</fieldset>

		<fieldset>
			<legend>Players</legend>
			<label class="row">
				<span>Number of players</span>
				<input
					type="number"
					name="players"
					min={game.min_players}
					max={game.max_players}
					step="1"
					required
					value={seatCount}
					oninput={(e) => (players = Number(e.currentTarget.value))}
					aria-describedby="players-hint"
				/>
			</label>
			<p class="hint" id="players-hint">
				{gameName(game.id)} takes {game.min_players} to {game.max_players} players.
			</p>
			{#if errors.players}<p class="field-error">{errors.players}</p>{/if}

			<ol class="seats" data-testid="seats">
				{#each Array.from({ length: seatCount }, (_, i) => `p${i + 1}`) as seat (seat)}
					<li>
						<span class="seat">{seat}</span>
						<label>
							<span class="sr-only">Player of {seat}</span>
							<select name="seat" aria-label="Player of {seat}">
								<option value={BOT} selected>Random bot</option>
								{#if setup?.models.length}
									<optgroup label="Models (not available yet)">
										{#each setup.models as model (model.id)}
											<option value={model.id} disabled={!setup.model_seats}>{model.id}</option>
										{/each}
									</optgroup>
								{/if}
							</select>
						</label>
						<label>
							<span class="sr-only">Personality of {seat}</span>
							<select
								aria-label="Personality of {seat}"
								disabled={!setup?.model_seats}
								title="Personalities shape how a model plays; bots have none"
							>
								<option value="">No personality</option>
								{#each setup?.personalities ?? [] as personality (personality.id)}
									<option value={personality.id}>{personality.name}</option>
								{/each}
							</select>
						</label>
					</li>
				{/each}
			</ol>
			<p class="hint">
				Every seat is a random bot for now: real models take seats once their connection is switched
				on (roadmap phase 2). Until then models and personalities are listed, not selectable.
			</p>
			{#if errors.seats}<p class="field-error">{errors.seats}</p>{/if}
		</fieldset>

		{#if game.id === 'werewolf'}
			{#if errors.roles}<p class="field-error" role="alert">{errors.roles}</p>{/if}
			<WerewolfRoles
				players={seatCount}
				roles={werewolfRoles}
				initialMode={form?.values?.ww_mode || DEFAULT_TEMPLATE}
				initialCounts={enteredCounts}
				serverProblems={form?.problems ?? []}
			/>
		{/if}

		<fieldset>
			<legend>Settings</legend>
			<label class="row">
				<span>Language</span>
				<select name="language" value={form?.values?.language || 'de'}>
					{#each LANGUAGES as language (language.id)}
						<option value={language.id}>{language.label}</option>
					{/each}
				</select>
			</label>
			<p class="hint">
				{GAMES_WITH_LANGUAGE.has(game.id)
					? 'The language of the narrator and of the players.'
					: 'This game has no game text yet; the setting matters once models play.'}
			</p>
			{#if errors.language}<p class="field-error">{errors.language}</p>{/if}

			<label class="row">
				<span>Speed</span>
				<select name="turn_delay" value={Number(form?.values?.turn_delay) || DEFAULT_TURN_DELAY}>
					{#each SPEEDS as speed (speed.turn_delay)}
						<option value={speed.turn_delay}>{speed.label} ({speed.turn_delay} s per turn)</option>
					{/each}
				</select>
			</label>
			<p class="hint">You can change it while the match runs.</p>
			{#if errors.turn_delay}<p class="field-error">{errors.turn_delay}</p>{/if}

			<label class="row">
				<span>Seed</span>
				<input
					type="number"
					name="seed"
					min="0"
					step="1"
					placeholder="random"
					value={form?.values?.seed ?? ''}
				/>
			</label>
			<p class="hint">The same seed with the same players plays the same match.</p>
			{#if errors.seed}<p class="field-error">{errors.seed}</p>{/if}

			<label class="row">
				<input
					type="checkbox"
					name="no_memory"
					checked={form?.values?.no_memory === 'on'}
					aria-describedby="memory-hint"
				/>
				<span>Play without memory (fair benchmark)</span>
			</label>
			<p class="hint" id="memory-hint">
				With memory, players remember this match: trust in the others and a short summary, and they
				bring it to later matches. Without it, nothing is read or written.
			</p>

			<label class="row">
				<span>Cost limit (€)</span>
				<input
					type="number"
					value={setup?.caps.match_eur ?? ''}
					min="0.01"
					max={setup?.caps.month_eur}
					step="0.01"
					disabled={!setup?.model_seats}
					aria-describedby="cost-hint"
				/>
			</label>
			<p class="hint" id="cost-hint">
				Bots cost nothing. With models, a match pauses before a call that could pass
				{setup ? `${setup.caps.match_eur.toFixed(2)} €` : 'the cap'}; all matches of a month stop at {setup
					? `${setup.caps.month_eur.toFixed(2)} €`
					: 'the monthly cap'}.
			</p>
		</fieldset>

		<button type="submit" disabled={submitting}>
			{submitting ? 'Starting…' : 'Start match'}
		</button>
	</form>
{/if}

<style>
	h1 {
		margin: 1.25rem 0 1rem;
		font-size: clamp(1.6rem, 5vw, 2.4rem);
	}

	form {
		display: grid;
		gap: 1.25rem;
		max-width: 44rem;
		padding-bottom: 2rem;
	}

	fieldset {
		display: grid;
		gap: 0.5rem;
		margin: 0;
		padding: 1rem;
		border-radius: var(--radius);
		background: var(--surface);
		border: 1px solid var(--border);
		min-width: 0;
	}

	legend {
		padding: 0 0.4rem;
		font-weight: 600;
	}

	.games {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
		gap: 0.5rem;
	}

	.game {
		display: grid;
		gap: 0.1rem;
		padding: 0.7rem 0.8rem;
		border-radius: var(--radius);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		cursor: pointer;
	}

	.game.chosen {
		border-color: var(--accent);
	}

	.game input {
		position: absolute;
		opacity: 0;
		pointer-events: none;
	}

	.game:has(input:focus-visible) {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.game small,
	.hint {
		color: var(--muted);
	}

	.hint,
	.field-error,
	.problem {
		margin: 0;
		font-size: 0.9rem;
	}

	.row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.75rem;
	}

	.row span {
		min-width: 9rem;
	}

	input,
	select,
	button {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.35rem 0.7rem;
		min-height: 2.25rem;
		max-width: 100%;
	}

	input:disabled,
	select:disabled {
		opacity: 0.6;
	}

	.seats {
		display: grid;
		gap: 0.4rem;
		margin: 0.25rem 0;
		padding: 0;
		list-style: none;
	}

	.seats li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem;
	}

	.seat {
		min-width: 2.5rem;
		font-weight: 600;
	}

	.field-error,
	.problem {
		color: var(--danger);
	}

	button[type='submit'] {
		justify-self: start;
		padding: 0.55rem 1.4rem;
		background: var(--accent);
		color: #1b1405;
		border-color: var(--accent);
		font-weight: 700;
		cursor: pointer;
	}

	button:disabled {
		opacity: 0.7;
		cursor: progress;
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}
</style>
