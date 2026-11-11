<script lang="ts">
	import type {
		Balance,
		SelectionProblem,
		SelectionReport,
		WerewolfRole,
		WerewolfTemplate
	} from '#lib/api.js';
	import { CUSTOM, DEFAULT_TEMPLATE, roleField } from '#lib/new-match.js';

	/**
	 * The Werewolf role selection of the new-match form: a template, or a
	 * checklist with counts. Free seats become villagers. The arena checks every
	 * change (through the web server) and the problems show next to their role.
	 */
	let {
		players,
		roles,
		initialMode = DEFAULT_TEMPLATE,
		initialCounts = {},
		serverProblems = []
	}: {
		players: number;
		roles: WerewolfRole[];
		initialMode?: string;
		initialCounts?: Record<string, number>;
		serverProblems?: SelectionProblem[];
	} = $props();

	const FILL = 'villager';
	const TEAMS = [
		{ id: 'wolves', label: 'Wolves' },
		{ id: 'solo', label: 'Alone' },
		{ id: 'village', label: 'Village' }
	] as const;

	// svelte-ignore state_referenced_locally
	let mode = $state(initialMode);
	// svelte-ignore state_referenced_locally
	let counts = $state<Record<string, number>>({ ...initialCounts });
	let templates = $state<WerewolfTemplate[]>([]);
	let report = $state<SelectionReport | null>(null);
	let unreachable = $state(false);

	const template = $derived(templates.find((t) => t.id === mode));
	// Until the templates have loaded (or without JavaScript), the default one.
	const templateOptions = $derived(
		templates.length
			? templates
			: [
					{
						id: DEFAULT_TEMPLATE,
						name: DEFAULT_TEMPLATE,
						min_players: 6,
						random: false,
						selection: {}
					}
				]
	);
	const villagerName = $derived(roles.find((role) => role.id === FILL)?.name ?? FILL);
	const choosable = $derived(roles.filter((role) => role.id !== FILL));
	const chosen = $derived(Object.values(counts).reduce((sum, n) => sum + (n || 0), 0));
	const villagers = $derived(report?.selection[FILL] ?? Math.max(0, players - chosen));
	// Problems of the last check; after a refused submit, those of the server until the next check.
	const problems = $derived(report ? report.problems : serverProblems);
	const general = $derived(problems.filter((p) => !p.role));
	const ofRole = (id: string) => problems.filter((p) => p.role === id);
	const shownBalance = $derived<Balance | null>(
		mode === CUSTOM ? (report?.balance ?? null) : (template?.balance ?? null)
	);

	/** The roles of a template, without the villagers that fill the table. */
	function withoutFill(selection: Record<string, number>) {
		return Object.fromEntries(Object.entries(selection).filter(([id]) => id !== FILL));
	}

	// The templates at this table size; a template in use follows the size.
	$effect(() => {
		const size = players;
		const controller = new AbortController();
		fetch(`/matches/new/werewolf?players=${size}`, { signal: controller.signal })
			.then((response) => (response.ok ? response.json() : Promise.reject()))
			.then((list: WerewolfTemplate[]) => {
				templates = list;
				unreachable = false;
				const current = list.find((t) => t.id === mode);
				if (current?.selection) counts = withoutFill(current.selection);
				else if (current && !current.random) mode = CUSTOM; // does not fit this table
			})
			.catch((error) => {
				if (error?.name !== 'AbortError') unreachable = true;
			});
		return () => controller.abort();
	});

	// Check a custom selection a moment after each change.
	$effect(() => {
		if (mode !== CUSTOM) {
			report = null;
			return;
		}
		const body = JSON.stringify({ roles: { ...counts }, players });
		const controller = new AbortController();
		const timer = setTimeout(() => {
			fetch('/matches/new/werewolf', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body,
				signal: controller.signal
			})
				.then((response) => (response.ok ? response.json() : Promise.reject()))
				.then((checked: SelectionReport) => {
					report = checked;
					unreachable = false;
				})
				.catch((error) => {
					if (error?.name !== 'AbortError') unreachable = true;
				});
		}, 250);
		return () => {
			clearTimeout(timer);
			controller.abort();
		};
	});

	function chooseTemplate(id: string) {
		mode = id;
		const picked = templates.find((t) => t.id === id);
		if (picked?.selection) counts = withoutFill(picked.selection);
	}

	function setCount(id: string, value: number) {
		counts = { ...counts, [id]: Number.isFinite(value) ? value : 0 };
		mode = CUSTOM;
	}

	const VERDICTS = {
		village: 'favours the village',
		even: 'even',
		wolves: 'favours the wolves'
	} as const;
</script>

<fieldset class="roles" data-testid="werewolf-roles">
	<legend>Roles</legend>

	<label class="row">
		<span>Template</span>
		<select name="ww_mode" value={mode} onchange={(e) => chooseTemplate(e.currentTarget.value)}>
			{#each templateOptions as option (option.id)}
				<option value={option.id} disabled={!option.random && option.selection === null}>
					{option.name}{!option.random && option.selection === null
						? ` (from ${option.min_players} players)`
						: ''}
				</option>
			{/each}
			<option value={CUSTOM}>Custom</option>
		</select>
	</label>

	{#if shownBalance}
		<p class="balance" data-verdict={shownBalance.verdict} data-testid="balance">
			<span class="light" aria-hidden="true"></span>
			Balance {shownBalance.total > 0 ? '+' : ''}{shownBalance.total}: {VERDICTS[
				shownBalance.verdict
			]}
		</p>
	{/if}
	{#if unreachable}
		<p class="field-error" role="status">
			The roles could not be checked: the arena did not answer.
		</p>
	{/if}
	{#if general.length}
		<ul class="problems" data-testid="selection-problems">
			{#each general as problem (problem.code + problem.message)}
				<li class="field-error">{problem.message}</li>
			{/each}
		</ul>
	{/if}

	{#if template?.random}
		<p class="hint">The roles are drawn from the match seed at the start: an even mix.</p>
	{:else}
		<p class="hint">
			Change a count to build your own mix. Free seats become villagers; {villagers} at this table.
		</p>
		{#each TEAMS as team (team.id)}
			{@const members = choosable.filter((role) => role.team === team.id)}
			{#if members.length}
				<h3>{team.label}</h3>
				<ul class="checklist">
					{#each members as role (role.id)}
						{@const count = counts[role.id] ?? 0}
						<li class:on={count > 0} data-role={role.id}>
							{#if role.unique}
								<label>
									<input
										type="checkbox"
										name={roleField(role.id)}
										value="1"
										checked={count > 0}
										onchange={(e) => setCount(role.id, e.currentTarget.checked ? 1 : 0)}
									/>
									<strong>{role.name}</strong>
								</label>
							{:else}
								<label>
									<input
										type="number"
										name={roleField(role.id)}
										min="0"
										max={players}
										step="1"
										value={count}
										aria-label="{role.name} count"
										oninput={(e) => setCount(role.id, e.currentTarget.valueAsNumber)}
									/>
									<strong>{role.name}</strong>
								</label>
							{/if}
							<small class="weight">{role.weight > 0 ? '+' : ''}{role.weight}</small>
							<small class="description">{role.description}</small>
							{#each ofRole(role.id) as problem (problem.code)}
								<span class="field-error">{problem.message}</span>
							{/each}
						</li>
					{/each}
				</ul>
			{/if}
		{/each}
		<p class="villagers" data-testid="villagers">{villagerName}: {villagers}</p>
	{/if}
</fieldset>

<style>
	.roles {
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

	h3 {
		margin: 0.5rem 0 0;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--muted);
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

	select,
	input[type='number'] {
		font: inherit;
		color: var(--text);
		background: var(--surface-raised);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 0.3rem 0.5rem;
		min-height: 2.25rem;
		max-width: 100%;
	}

	input[type='number'] {
		width: 4rem;
	}

	input[type='checkbox'] {
		width: 1.2rem;
		height: 1.2rem;
		accent-color: var(--accent);
	}

	.checklist {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 0.4rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.checklist li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.2rem 0.5rem;
		padding: 0.5rem 0.6rem;
		border-radius: 8px;
		background: var(--surface-raised);
		border: 1px solid var(--border);
	}

	.checklist li.on {
		border-color: var(--accent);
	}

	.checklist label {
		display: inline-flex;
		align-items: center;
		gap: 0.45rem;
		cursor: pointer;
	}

	.weight {
		margin-left: auto;
		color: var(--muted);
	}

	.description {
		flex-basis: 100%;
		color: var(--muted);
	}

	.hint,
	.villagers {
		margin: 0;
		color: var(--muted);
		font-size: 0.9rem;
	}

	.field-error {
		color: var(--danger);
		font-size: 0.9rem;
	}

	.checklist .field-error {
		flex-basis: 100%;
	}

	.problems {
		margin: 0;
		padding-left: 1.1rem;
	}

	.balance {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0;
	}

	.light {
		width: 0.9rem;
		height: 0.9rem;
		border-radius: 50%;
		background: #7ad69a;
		box-shadow: 0 0 0.5rem #7ad69a;
	}

	.balance[data-verdict='village'] .light,
	.balance[data-verdict='wolves'] .light {
		background: var(--accent);
		box-shadow: 0 0 0.5rem var(--accent);
	}
</style>
