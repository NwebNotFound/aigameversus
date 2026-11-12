/** Pure helpers of the Werewolf circle: seat positions, day or night, and the votes to draw. */
import type { MatchEvent } from '../api.js';

export interface Point {
	/** Percent of the circle's box. */
	left: number;
	top: number;
}

/** Where seat `index` of `count` sits on the circle: the first at the top, then clockwise. */
export function circlePoint(index: number, count: number): Point {
	const angle = (index / count) * 2 * Math.PI;
	return {
		left: Math.round((50 + 38 * Math.sin(angle)) * 10) / 10,
		top: Math.round((50 - 38 * Math.cos(angle)) * 10) / 10
	};
}

export type Theme = 'night' | 'dusk' | 'day';

/** The look of the circle for a phase of the plugin: night, dusk (before the night) or day. */
export function themeOf(phase: unknown): Theme {
	if (phase === 'night') return 'night';
	if (phase === 'dusk') return 'dusk';
	return 'day';
}

export interface Vote {
	from: string;
	to: string;
}

/**
 * The votes to draw: those cast since the day began, one per voter (the last one counts).
 * They stay on the board after the result and until the next night starts.
 */
export function currentVotes(events: MatchEvent[]): Vote[] {
	let votes = new Map<string, string>();
	for (const event of events) {
		if (event.type === 'day_started' || event.type === 'night_started') votes = new Map();
		else if (event.type === 'vote_cast') {
			const { player, target } = event.data;
			if (typeof player !== 'string') continue;
			if (typeof target === 'string') votes.set(player, target);
			else votes.delete(player); // an abstention takes a vote back
		}
	}
	return [...votes].map(([from, to]) => ({ from, to }));
}

/** How many votes each player has against them. */
export function tally(votes: Vote[]): Record<string, number> {
	const counts: Record<string, number> = {};
	for (const { to } of votes) counts[to] = (counts[to] ?? 0) + 1;
	return counts;
}

/** A role id as a word: "bear_tamer" becomes "Bear tamer". */
export function roleName(role: unknown): string {
	if (typeof role !== 'string' || !role) return '?';
	const words = role.replaceAll('_', ' ');
	return words[0].toUpperCase() + words.slice(1);
}

const WOLF_ROLES = new Set(['werewolf', 'prime_wolf', 'white_wolf']);

/** Whether a role hunts with the pack, for the colour of its label. */
export const isWolf = (role: unknown) => typeof role === 'string' && WOLF_ROLES.has(role);

export interface Death {
	role: string | null;
	cause: string | null;
	/** Which death of the match it was, from 1, for the order of the reveal. */
	order: number;
}

/**
 * Who has died, with the role the game announced at the death (`player_died` is public, so
 * this holds in the spoiler-free view too) and how they died.
 */
export function deathsOf(events: MatchEvent[]): Record<string, Death> {
	const deaths: Record<string, Death> = {};
	let order = 0;
	for (const event of events) {
		if (event.type !== 'player_died') continue;
		const { player, role, cause } = event.data as Record<string, unknown>;
		if (typeof player !== 'string' || deaths[player]) continue;
		deaths[player] = {
			role: typeof role === 'string' ? role : null,
			cause: typeof cause === 'string' ? cause : null,
			order: ++order
		};
	}
	return deaths;
}

/** How a death reads on the seat: "killed at night", "executed", … */
export function causeWords(cause: string | null): string {
	switch (cause) {
		case 'wolves':
			return 'killed at night';
		case 'executed':
			return 'executed';
		case 'poison':
		case 'poisoned':
			return 'poisoned';
		case 'hunter':
		case 'shot':
			return 'shot';
		case null:
			return 'died';
		default:
			return cause.replaceAll('_', ' ');
	}
}

/** Events that end what was said: a new phase, a vote result, a death. */
const SCENE_ENDS = new Set([
	'night_started',
	'morning_started',
	'day_started',
	'vote_result',
	'player_died',
	'game_over'
]);

/**
 * The words on stage: the newest speech (or pack whisper) line, as long as no later line
 * ended its scene. The board draws it at the speaker's seat; the commentary keeps them all.
 */
export function onStage<
	L extends { kind: string; actor: string | null; raw: Record<string, unknown> }
>(lines: L[]): L | null {
	for (let i = lines.length - 1; i >= 0; i--) {
		const line = lines[i];
		if ((line.kind === 'speech' || line.kind === 'whisper') && line.actor) return line;
		if (SCENE_ENDS.has(String(line.raw?.type ?? ''))) return null;
	}
	return null;
}

/** The tally as a ranking, most votes first, then by seat order. */
export function ranking(votes: Vote[], order: string[]): { player: string; votes: number }[] {
	const counts = tally(votes);
	return Object.entries(counts)
		.map(([player, n]) => ({ player, votes: n }))
		.sort((a, b) => b.votes - a.votes || order.indexOf(a.player) - order.indexOf(b.player));
}

/** One line of the game master (#117): the event's position in the full log, its kind, its words. */
export interface Narration {
	seq: number;
	key: string;
	text: Record<string, string>;
}

export interface Recap {
	seq: number;
	key: string;
	text: string;
}

/**
 * What the game master says about the scene on screen: the newest narration up to the
 * event at `lastSeq`, in `lang`. The arena's dramatic lines (analytics `narration`) come
 * first; without them the transcript's own narration line stands in. Null while a player
 * speaks (the stage is theirs) or before anything was narrated.
 */
export function recapOf<
	L extends { kind: string; seq: number | null; text: string; raw: Record<string, unknown> }
>(
	narration: Narration[] | null,
	lines: L[],
	lastSeq: number | null,
	lang: string,
	speaking: boolean
): Recap | null {
	if (speaking || lastSeq === null) return null;
	const told = (narration ?? []).filter((n) => n.seq <= lastSeq).at(-1);
	if (told) return { seq: told.seq, key: told.key, text: told.text[lang] ?? told.text.en ?? '' };
	const line = lines
		.filter((l) => l.kind === 'narration' && l.seq !== null && l.seq <= lastSeq)
		.at(-1);
	if (!line || line.seq === null) return null;
	const key = (line.raw?.data as { key?: unknown } | undefined)?.key;
	return { seq: line.seq, key: typeof key === 'string' ? key : 'narration', text: line.text };
}

/** The label above a recap, by its key. */
export function recapLabel(key: string): string {
	if (key === 'night_falls') return 'Nightfall';
	if (key.startsWith('morning')) return 'Morning';
	if (key === 'execution' || key === 'no_execution') return 'The vote';
	if (key.startsWith('captain')) return 'The captain';
	if (key === 'game_over') return 'The end';
	return 'The village';
}
