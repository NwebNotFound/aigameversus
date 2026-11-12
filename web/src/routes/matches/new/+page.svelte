<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import {
		cheapSeats,
		loadFavourites,
		reliabilityNote,
		saveFavourites,
		unreliable
	} from '#lib/catalog.js';
	import ModelPicker from '#lib/components/ModelPicker.svelte';
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
	let gameId = $state(form?.values?.game || page.url.searchParams.get('game') || 'liars_deck');
	const game = $derived(games.find((g) => g.id === gameId) ?? games[0]);
	// svelte-ignore state_referenced_locally
	let players = $state(Number(form?.values?.players) || 0);
	const seatCount = $derived(
		game ? Math.min(Math.max(players || game.min_players, game.min_players), game.max_players) : 0
	);
	let submitting = $state(false);

	// Who takes each seat: a random bot or a model id. A match is all bots or all models.
	let choices = $state<string[]>([]);
	// Every seat has a choice before a picker binds to it: a new seat starts as a bot.
	$effect.pre(() => {
		if (choices.length < seatCount) {
			choices = [...choices, ...Array(seatCount - choices.length).fill(BOT)];
		}
	});
	// Every model that can take a seat (GET /models/catalog); the verified ones without it.
	const catalog = $derived(
		data.catalog.state === 'ok'
			? data.catalog.data.models
			: (setup?.models ?? []).map((m) => ({
					id: m.id,
					openrouter_id: m.model,
					name: m.name,
					vendor: m.model.split('/')[0],
					context_length: null,
					input_usd_per_mtok: m.input_usd_per_mtok,
					output_usd_per_mtok: m.output_usd_per_mtok,
					reasoning: false,
					moderated: false,
					free: false,
					verified: true,
					high_price: m.output_usd_per_mtok > 10,
					price_source: 'config/models.yaml'
				}))
	);
	const seatIds = $derived(Array.from({ length: seatCount }, (_, i) => choices[i] ?? BOT));
	const expensive = $derived(
		catalog.filter((m) => m.high_price && seatIds.includes(m.id)).map((m) => m.name)
	);
	const unverified = $derived(
		catalog.filter((m) => !m.verified && seatIds.includes(m.id)).map((m) => m.name)
	);
	const shaky = $derived(catalog.filter((m) => unreliable(m) && seatIds.includes(m.id)));

	let favourites = $state(new Set<string>());
	onMount(() => (favourites = loadFavourites(localStorage)));
	function toggleFavourite(id: string) {
		const next = new Set(favourites);
		if (next.has(id)) next.delete(id);
		else next.add(id);
		favourites = next;
		saveFavourites(localStorage, next);
	}

	function sameInAllSeats() {
		const first = choices[0] ?? BOT;
		choices = Array.from({ length: seatCount }, () => first);
	}

	function fillCheap() {
		const cheap = cheapSeats(catalog, seatCount);
		if (cheap.length) choices = cheap;
	}
	const usesModels = $derived(
		Array.from({ length: seatCount }, (_, i) => choices[i] ?? BOT).some((c) => c !== BOT)
	);
	const month = $derived(data.month.state === 'ok' ? data.month.data : null);
	const matchCap = $derived(setup ? Math.round(setup.caps.match_eur * 1_000_000) : 0);
	// A match of models cannot start when the month is used up, or when its spend is unknown.
	const monthEmpty = $derived(usesModels && month !== null && month.remaining_micro_eur <= 0);
	const blocked = $derived(usesModels && (month === null || month.remaining_micro_eur <= 0));
	const euro = (micro: number) => `${(micro / 1_000_000).toFixed(2)} €`;

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
				{#each Array.from({ length: seatCount }, (_, i) => `p${i + 1}`) as seat, index (seat)}
					<li>
						<span class="seat">{seat}</span>
						<ModelPicker
							{seat}
							bind:value={choices[index]}
							models={catalog}
							enabled={setup?.model_seats ?? false}
							{favourites}
							ontogglefavourite={toggleFavourite}
						/>
						<label>
							<span class="sr-only">Personality of {seat}</span>
							<select
								name="personality_{seat}"
								aria-label="Personality of {seat}"
								disabled={!setup?.seat_personalities ||
									!setup.model_seats ||
									seatIds[index] === BOT}
								title={setup?.seat_personalities
									? 'A personality for this model; a random bot plays none'
									: 'Not possible yet: the live arena does not take a personality per seat'}
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
			{#if setup?.model_seats}
				<div class="shortcuts" role="group" aria-label="Seat shortcuts">
					<button type="button" onclick={sameInAllSeats}>Same as p1 in every seat</button>
					<button type="button" onclick={fillCheap}>Fill with cheap models</button>
					<button
						type="button"
						onclick={() => (choices = Array.from({ length: seatCount }, () => BOT))}
					>
						All random bots
					</button>
				</div>
			{/if}
			{#if shaky.length}
				<div class="field-error" role="alert" data-testid="unreliable-models">
					<p>
						Unreliable in this arena: {#each shaky as model, i (model.id)}{i ? ', ' : ''}<span
								title={reliabilityNote(model)}>{model.name}</span
							>{/each}. Such a model often fails or is replaced by the random bot.
					</p>
					<label>
						<input type="checkbox" name="confirm_unreliable" />
						Seat {shaky.length === 1 ? 'it' : 'them'} anyway
					</label>
					{#if errors.confirm_unreliable}<p>{errors.confirm_unreliable}</p>{/if}
				</div>
			{/if}
			{#if expensive.length}
				<p class="field-error" role="alert" data-testid="high-price">
					Expensive: {expensive.join(', ')} cost{expensive.length === 1 ? 's' : ''} more than $10 per
					million output tokens; the match still stops at its cap.
				</p>
			{/if}
			{#if unverified.length}
				<p class="hint" data-testid="unverified">
					Price not checked, budgeted +25%: {unverified.join(', ')}. The caps count OpenRouter's
					listed price plus 25%, and these models may handle the tools less well.
				</p>
			{/if}
			<p class="hint">
				{#if setup?.model_seats && setup.mixed_seats}
					Each seat is a model (paid) or a random bot (free); a table may mix them, and a model may
					play a personality.
				{:else if setup?.model_seats}
					A table is all models (paid) or all random bots (free). Not possible yet: bots and models
					at one table, and a personality per seat; both need an arena update that is not live.
				{:else}
					This server plays random bots only: it was not started with model seats on, or it has no
					API key. Models and personalities are listed, not selectable.
				{/if}
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
					: 'This game plays in English for now: only Werewolf takes a language (its narrator and the table talk).'}
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

			{#if usesModels && setup?.answer_repair?.includes('v1')}
				<input type="hidden" name="answer_repair_offered" value="1" />
				<label class="row" data-testid="answer-repair">
					<input
						type="checkbox"
						name="answer_repair"
						checked={form?.values ? form.values.answer_repair === 'on' : true}
						aria-describedby="repair-hint"
					/>
					<span>Repair garbled tool calls</span>
				</label>
				<p class="hint" id="repair-hint">
					A model's call that is garbled but clear (extra text, numbers as words, an extra field) is
					read as the move it means, and marked so. Research runs keep this off.
				</p>
			{/if}

			{#if usesModels}
				<div class="spend" data-testid="spend" role="group" aria-label="Spending">
					<p>
						<strong>This match spends real money.</strong> It costs at most
						<strong data-testid="match-cap">{euro(matchCap)}</strong>: it stops before a call that
						could pass that.
					</p>
					{#if month}
						<p data-testid="month">
							This month: {euro(month.spent_micro_eur)} spent of {euro(month.cap_micro_eur)},
							<strong>{euro(month.remaining_micro_eur)} left</strong>.
						</p>
						{#if monthEmpty}
							<p class="field-error" role="alert" data-testid="month-empty">
								Nothing is left this month: a match of models cannot start.
							</p>
						{:else if month.remaining_micro_eur < matchCap}
							<p class="field-error" data-testid="month-low">
								Less is left this month than one match may cost; it stops when the month runs out.
							</p>
						{/if}
					{:else}
						<p class="field-error" role="alert" data-testid="month-unknown">
							The spending of this month is unknown: a match of models cannot start.
						</p>
					{/if}
					<label class="row confirm">
						<input type="checkbox" name="confirm_spend" />
						<span>I understand that this match spends money, up to {euro(matchCap)}.</span>
					</label>
					{#if errors.confirm_spend}<p class="field-error">{errors.confirm_spend}</p>{/if}
				</div>
			{:else}
				<p class="hint">Bots cost nothing.</p>
			{/if}
		</fieldset>

		<button type="submit" disabled={submitting || blocked}>
			{submitting ? 'Starting…' : usesModels ? 'Start match (spends money)' : 'Start match'}
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
		align-items: flex-start;
		gap: 0.4rem;
	}

	.seat {
		min-width: 2.5rem;
		font-weight: 600;
		padding-top: 0.45rem;
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

	.spend {
		display: grid;
		gap: 0.4rem;
		padding: 0.75rem 0.9rem;
		border-radius: var(--radius);
		border: 1px solid var(--accent);
		background: color-mix(in srgb, var(--accent) 10%, var(--surface));
	}

	.spend p {
		margin: 0;
	}

	.shortcuts {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}

	.shortcuts button {
		font-size: 0.9rem;
		padding: 0.25rem 0.6rem;
		cursor: pointer;
	}
</style>
