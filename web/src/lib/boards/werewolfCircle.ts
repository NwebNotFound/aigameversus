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
