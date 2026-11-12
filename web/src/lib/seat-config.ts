/**
 * The configuration of one model seat in the new-match form: what each option means, the
 * presets, and what the form sends for it.
 *
 * Every option starts as "default": the seat plays as the arena would play it without the
 * panel. The arena lists the options it takes per seat (`GET /setup`, `seat_options`); the
 * form sends a changed option only when the arena takes it, so an arena without them gets
 * the same request as before. Spoiler-safe: nothing here reads a match.
 */

/** What `max_output_tokens` may be: the arena's limit, a number, or the adaptive limit. */
export type Output = 'default' | 'adaptive' | number;
export type Reasoning = 'default' | 'off' | 'low' | 'medium' | 'high';
export type Toggle = 'default' | 'on' | 'off';
export type Repair = 'default' | 'off' | 'v1' | 'v2';

export interface SeatConfig {
	max_output_tokens: Output;
	reasoning_effort: Reasoning;
	/** null: the model's own default. */
	temperature: number | null;
	/** Extra strategy text for this seat's prompt; empty for none. */
	strategy: string;
	memory: Toggle;
	answer_repair: Repair;
	thought_headline: Toggle;
	private_plan: Toggle;
}

export type OptionKey = keyof SeatConfig;

export const DEFAULT: Readonly<SeatConfig> = Object.freeze({
	max_output_tokens: 'default',
	reasoning_effort: 'default',
	temperature: null,
	strategy: '',
	memory: 'default',
	answer_repair: 'default',
	thought_headline: 'default',
	private_plan: 'default'
});

export const MAX_STRATEGY = 600; // characters of strategy text per seat
export const OUTPUT_RANGE = { min: 64, max: 8000 };
export const TEMPERATURE_RANGE = { min: 0, max: 2, step: 0.1 };

/** One option as the panel shows it: its label, a short help line and its choices. */
export interface OptionInfo {
	key: OptionKey;
	label: string;
	help: string;
	/** The choices of a select; a number field or text has none. */
	choices?: { value: string; label: string }[];
	/** Shown only for these games; every game when missing. */
	games?: string[];
}

const TOGGLE = [
	{ value: 'default', label: 'Default' },
	{ value: 'on', label: 'On' },
	{ value: 'off', label: 'Off' }
];

export const OPTIONS: OptionInfo[] = [
	{
		key: 'max_output_tokens',
		label: 'Answer length',
		help: 'The most a model may write per answer, its thinking included. Adaptive starts short and allows more after an answer was cut off. Shorter is cheaper; too short and answers break off.',
		choices: [
			{ value: 'default', label: 'Default (the arena limit)' },
			{ value: 'adaptive', label: 'Adaptive' },
			{ value: 'custom', label: 'Custom number of tokens' }
		]
	},
	{
		key: 'reasoning_effort',
		label: 'Thinking',
		help: 'How long a reasoning model thinks before it answers. More thinking costs more and takes longer; models without reasoning ignore it.',
		choices: [
			{ value: 'default', label: 'Default' },
			{ value: 'off', label: 'Off' },
			{ value: 'low', label: 'Low' },
			{ value: 'medium', label: 'Medium' },
			{ value: 'high', label: 'High' }
		]
	},
	{
		key: 'temperature',
		label: 'Temperature',
		help: 'How much the model varies its answers: low is steady, high is surprising. Empty keeps the model default; some models ignore it.'
	},
	{
		key: 'strategy',
		label: 'Strategy',
		help: 'A short instruction for this seat only, added to its prompt as the player\'s own plan (for example "Bluff rarely, call often"). The rules and the goal still come first.'
	},
	{
		key: 'memory',
		label: 'Memory',
		help: 'Whether this seat remembers the other players from earlier matches (trust and a short summary). Off makes it a fair benchmark seat.',
		choices: TOGGLE
	},
	{
		key: 'answer_repair',
		label: 'Answer repair',
		help: 'What happens to a garbled tool call: off plays it as sent, v1 reads it when the meaning is clear, v2 also asks Jev to map it to a legal move.',
		choices: [
			{ value: 'default', label: 'Default (the match setting)' },
			{ value: 'off', label: 'Off' },
			{ value: 'v1', label: 'v1: repair clear mistakes' },
			{ value: 'v2', label: 'v2: v1 and Jev' }
		]
	},
	{
		key: 'thought_headline',
		label: 'Thought headline',
		help: 'Every move also asks for a one-line headline of the thought, shown to viewers. A few more tokens per move.',
		choices: TOGGLE
	},
	{
		key: 'private_plan',
		label: 'Private plan',
		help: 'The nation keeps a short plan from round to round that only it reads.',
		choices: TOGGLE,
		games: ['civ']
	}
];

/** A preset: a name, what it is for, and the options it sets (the rest stay default). */
export interface Preset {
	id: string;
	label: string;
	help: string;
	config: Partial<SeatConfig>;
}

export const PRESETS: Preset[] = [
	{
		id: 'careful',
		label: 'Careful',
		help: 'Thinks longer, answers steadily, keeps a headline: better play, higher cost.',
		config: {
			reasoning_effort: 'high',
			max_output_tokens: 'adaptive',
			temperature: 0.2,
			thought_headline: 'on',
			strategy: 'Play carefully: weigh the risk of every move and avoid needless gambles.'
		}
	},
	{
		id: 'fast',
		label: 'Fast and cheap',
		help: 'Short answers, little thinking: cheapest per move, more mistakes.',
		config: {
			reasoning_effort: 'low',
			max_output_tokens: 400,
			thought_headline: 'off'
		}
	},
	{
		id: 'aggressive',
		label: 'Aggressive',
		help: 'Bold and varied play: more bluffs and attacks.',
		config: {
			temperature: 0.9,
			strategy:
				'Play aggressively: take the initiative, bluff and attack when it may pay off, and do not wait for a perfect moment.'
		}
	}
];

/** A fresh configuration: the defaults, or a preset on top of them. */
export function configOf(preset?: string): SeatConfig {
	const found = PRESETS.find((p) => p.id === preset);
	return { ...DEFAULT, ...(found?.config ?? {}) };
}

/** Whether an option is at its default. */
export function isDefault(config: SeatConfig, key: OptionKey): boolean {
	return config[key] === DEFAULT[key];
}

/** The options a seat changed, in panel order. */
export function changed(config: SeatConfig): OptionKey[] {
	return OPTIONS.map((o) => o.key).filter((key) => !isDefault(config, key));
}

/** The preset a configuration is exactly, if any. */
export function presetOf(config: SeatConfig): Preset | undefined {
	return PRESETS.find((p) => {
		const want = configOf(p.id);
		return OPTIONS.every((o) => want[o.key] === config[o.key]);
	});
}

/** The short line on a closed panel: "Default", a preset's name, or the number of changes. */
export function summary(config: SeatConfig): string {
	const changes = changed(config).length;
	if (!changes) return 'Default';
	const preset = presetOf(config);
	if (preset) return preset.label;
	return changes === 1 ? '1 change' : `${changes} changes`;
}

/** Every seat set to one seat's configuration (a copy for each). */
export function applyToAll(configs: SeatConfig[], from: number): SeatConfig[] {
	const source = configs[from] ?? configOf();
	return configs.map(() => ({ ...source }));
}

/** One seat set to a copy of another's configuration. */
export function copyFrom(configs: SeatConfig[], to: number, from: number): SeatConfig[] {
	return configs.map((config, i) => (i === to ? { ...(configs[from] ?? config) } : config));
}

/** Why a value cannot be sent, or null. */
export function problem(config: SeatConfig): string | null {
	const out = config.max_output_tokens;
	if (typeof out === 'number') {
		if (!Number.isInteger(out) || out < OUTPUT_RANGE.min || out > OUTPUT_RANGE.max)
			return `Answer length is a whole number from ${OUTPUT_RANGE.min} to ${OUTPUT_RANGE.max} tokens.`;
	}
	const t = config.temperature;
	if (t !== null && (!Number.isFinite(t) || t < TEMPERATURE_RANGE.min || t > TEMPERATURE_RANGE.max))
		return `Temperature is a number from ${TEMPERATURE_RANGE.min} to ${TEMPERATURE_RANGE.max}.`;
	if (config.strategy.length > MAX_STRATEGY)
		return `Strategy is at most ${MAX_STRATEGY} characters.`;
	return null;
}

/**
 * The changed options of a seat that the arena takes (`supported`, from `GET /setup`) and that
 * apply to this game, as the form sends them; empty when nothing would change.
 */
export function overrides(
	config: SeatConfig,
	supported: readonly string[],
	game: string
): Partial<Record<OptionKey, unknown>> {
	const out: Partial<Record<OptionKey, unknown>> = {};
	for (const option of OPTIONS) {
		const key = option.key;
		if (isDefault(config, key) || !supported.includes(key)) continue;
		if (option.games && !option.games.includes(game)) continue;
		const value = config[key];
		out[key] = value === 'on' ? true : value === 'off' && option.choices === TOGGLE ? false : value;
	}
	if (typeof out.strategy === 'string') out.strategy = out.strategy.trim();
	return out;
}

/** A configuration read back from the form's hidden field; the defaults when it is not one. */
export function parseConfig(text: string | null | undefined): SeatConfig {
	if (!text) return configOf();
	try {
		const value = JSON.parse(text);
		if (typeof value !== 'object' || value === null) return configOf();
		const config = configOf();
		for (const key of Object.keys(DEFAULT) as OptionKey[]) {
			if (key in value) (config as Record<OptionKey, unknown>)[key] = value[key];
		}
		return config;
	} catch {
		return configOf();
	}
}
