/**
 * The playout director: how long each moment of a match stays on screen, so a match is
 * watchable whether its models answer in 30 seconds or in 30 milliseconds. Replays and the
 * live view both play moment by moment with these dwell times; the models' real waits are
 * never replayed (they show as a thinking timer live, and as a label afterwards).
 */
import type { TranscriptLine } from './api.js';
import { words } from './viewer.js';

/** Playback speeds, as factors of the reading pace. */
export const SPEEDS = [
	{ label: '0.5×', factor: 0.5 },
	{ label: '1×', factor: 1 },
	{ label: '2×', factor: 2 },
	{ label: '4×', factor: 4 }
] as const;

/** The quickest any moment flashes by, at any speed. */
export const FLOOR_MS = 120;

/** Reading time of something a player wrote: 0.3 s plus 60 ms a word, within 0.9 to 6 s. */
export function readingMs(text: string): number {
	const count = text.trim() ? text.trim().split(/\s+/).length : 0;
	return Math.min(6000, Math.max(900, 300 + 60 * count));
}

/** How long one line holds the screen at 1×. */
export function lineMs(line: TranscriptLine): number {
	if (line.kind === 'speech' || line.kind === 'whisper' || line.kind === 'thought') {
		return readingMs(words(line) ?? line.text);
	}
	if (line.importance === 3) return 2200; // a call, a shot, a death, a vote result
	if (line.kind === 'heading') return 1400; // a new round, hand, night or day
	if (line.kind === 'info' || line.importance === 1) return 250;
	return 1000; // a play, a bet, a vote
}

/**
 * The dwell of a moment that shows `lines` (everything that happened since the last
 * moment): the longest line, plus a little for each further line, at `speed`.
 */
export function dwellMs(lines: TranscriptLine[], speed: number): number {
	if (lines.length === 0) return Math.max(FLOOR_MS, 250 / speed);
	const longest = Math.max(...lines.map(lineMs));
	const extra = Math.min(1200, 200 * (lines.length - 1));
	return Math.max(FLOOR_MS, (longest + extra) / speed);
}

/** "12 s", "1 min 5 s": a running wait, for the thinking timer. */
export function waited(ms: number): string {
	const s = Math.max(0, Math.floor(ms / 1000));
	return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}
