import { describe, expect, it } from 'vitest';
import {
	DEFAULT,
	PRESETS,
	applyToAll,
	changed,
	configOf,
	copyFrom,
	overrides,
	parseConfig,
	presetOf,
	problem,
	summary
} from './seat-config.js';

const ALL = [
	'max_output_tokens',
	'reasoning_effort',
	'temperature',
	'strategy',
	'memory',
	'answer_repair',
	'thought_headline',
	'private_plan'
];

describe('seat configuration', () => {
	it('starts at the defaults, says so, and sends nothing', () => {
		const config = configOf();

		expect(config).toEqual(DEFAULT);
		expect(changed(config)).toEqual([]);
		expect(summary(config)).toBe('Default');
		expect(overrides(config, ALL, 'poker')).toEqual({});
	});

	it('names a preset when the seat is exactly it, else counts the changes', () => {
		for (const preset of PRESETS) expect(summary(configOf(preset.id))).toBe(preset.label);

		const tuned = { ...configOf('fast'), temperature: 0.5 };
		expect(presetOf(tuned)).toBeUndefined();
		expect(summary(tuned)).toBe(`${changed(tuned).length} changes`);
		expect(summary({ ...configOf(), memory: 'off' })).toBe('1 change');
	});

	it('sends only the changed options the arena takes, toggles as booleans', () => {
		const config = {
			...configOf(),
			reasoning_effort: 'high' as const,
			memory: 'off' as const,
			thought_headline: 'on' as const,
			answer_repair: 'off' as const,
			strategy: '  Bluff rarely.  '
		};

		expect(overrides(config, ['reasoning_effort', 'memory', 'strategy'], 'poker')).toEqual({
			reasoning_effort: 'high',
			memory: false,
			strategy: 'Bluff rarely.'
		});
		expect(overrides(config, ALL, 'poker')).toMatchObject({
			thought_headline: true,
			answer_repair: 'off' // a choice, not a toggle: it stays a word
		});
		expect(overrides(config, [], 'poker')).toEqual({});
	});

	it('leaves out an option of another game', () => {
		const config = { ...configOf(), private_plan: 'on' as const };

		expect(overrides(config, ALL, 'poker')).toEqual({});
		expect(overrides(config, ALL, 'civ')).toEqual({ private_plan: true });
	});

	it('copies one seat to another, and one seat to all, as copies', () => {
		const configs = [configOf('careful'), configOf(), configOf('aggressive')];

		const copied = copyFrom(configs, 1, 2);
		expect(copied[1]).toEqual(configs[2]);
		expect(copied[1]).not.toBe(configs[2]);
		expect(copied[0]).toBe(configs[0]);

		const all = applyToAll(configs, 0);
		expect(all.every((c) => summary(c) === 'Careful')).toBe(true);
		all[1].temperature = 1;
		expect(all[0].temperature).toBe(0.2); // not shared
	});

	it('refuses an answer length, temperature or strategy outside its range', () => {
		expect(problem({ ...configOf(), max_output_tokens: 10 })).toMatch(/Answer length/);
		expect(problem({ ...configOf(), max_output_tokens: 1.5 })).toMatch(/whole number/);
		expect(problem({ ...configOf(), temperature: 3 })).toMatch(/Temperature/);
		expect(problem({ ...configOf(), strategy: 'x'.repeat(601) })).toMatch(/600/);
		expect(problem(configOf('careful'))).toBeNull();
	});

	it('reads a configuration back from the form, the defaults for anything else', () => {
		const config = configOf('fast');

		expect(parseConfig(JSON.stringify(config))).toEqual(config);
		expect(parseConfig('{"temperature": 0.4, "unknown": 1}')).toEqual({
			...DEFAULT,
			temperature: 0.4
		});
		expect(parseConfig('not json')).toEqual(DEFAULT);
		expect(parseConfig('')).toEqual(DEFAULT);
		expect(parseConfig('[1]')).toEqual(DEFAULT);
	});
});
