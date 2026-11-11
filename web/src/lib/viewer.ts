/**
 * The watch screen (live view and replay): viewer modes, what reaches the browser in
 * each, and how transcript lines map onto the replay timeline.
 *
 * Text comes only from the transcript (`arena/transcript`); nothing here words an event.
 */
import type { MatchEvent, Seat, TranscriptLine } from './api.js';

/** Spectator view shows thoughts, hands and roles; spoiler-free shows what every player saw. */
export type View = 'spectator' | 'spoiler-free';

export function viewFrom(value: string | null): View {
	return value === 'spoiler-free' ? 'spoiler-free' : 'spectator';
}

/** The transcript language of a match: its `language` setting, English without one. */
export function langOf(settings: Record<string, unknown>): 'en' | 'de' {
	return settings.language === 'de' ? 'de' : 'en';
}

/** The lines that happened up to event position `lastSeq` (all when null). */
export function linesUpTo(lines: TranscriptLine[], lastSeq: number | null): TranscriptLine[] {
	if (lastSeq === null) return lines;
	return lines.filter((line) => line.seq === null || line.seq <= lastSeq);
}

/** Lines shown in the commentary: bookkeeping (importance 1) only when asked for. */
export function commentary(lines: TranscriptLine[], bookkeeping: boolean): TranscriptLine[] {
	return bookkeeping ? lines : lines.filter((line) => line.importance > 1 && line.kind !== 'info');
}

export interface Mark {
	/** The replay step at which the line has happened (its event shown). */
	step: number;
	line: TranscriptLine;
}

/**
 * Replay steps of chapter starts (`heading` lines) and highlights (importance 3).
 * Step n shows the first n events of `events`, so a line of event `seq` is shown from
 * the step after that event's index.
 */
export function marks(events: MatchEvent[], lines: TranscriptLine[]) {
	const stepOf = new Map(events.map((event, index) => [event.seq, index + 1]));
	const at = (line: TranscriptLine) => (line.seq === null ? undefined : stepOf.get(line.seq));
	const chapters: Mark[] = [];
	const highlights: Mark[] = [];
	for (const line of lines) {
		const step = at(line);
		if (step === undefined) continue;
		if (line.kind === 'heading') chapters.push({ step, line });
		else if (line.importance === 3) highlights.push({ step, line });
	}
	return { chapters, highlights };
}

/**
 * The replay steps worth stopping at, in order: steps whose event has a line of at least
 * importance `min` (chapter headings count as stops in both modes). Bookkeeping never stops.
 */
export function stops(events: MatchEvent[], lines: TranscriptLine[], min: 2 | 3): number[] {
	const weight = new Map<number, number>();
	for (const line of lines) {
		if (line.seq === null || (line.kind === 'info' && line.importance < 3)) continue;
		const value = line.kind === 'heading' ? 3 : line.importance;
		weight.set(line.seq, Math.max(value, weight.get(line.seq) ?? 0));
	}
	const result: number[] = [];
	events.forEach((event, index) => {
		if ((weight.get(event.seq) ?? 0) >= min) result.push(index + 1);
	});
	return result;
}

/** The first stop after `from`, or the end. */
export function nextStop(all: number[], from: number, end: number): number {
	return all.find((step) => step > from) ?? end;
}

/** The last stop before `from`, or the start. */
export function previousStop(all: number[], from: number): number {
	return all.findLast((step) => step < from) ?? 0;
}

/**
 * A short label for a numbered chapter on the timeline: "R3", "H12", "N2", "D2".
 * Null for a heading without a number (a poker street), which is a tick only.
 */
export function chapterLabel(line: TranscriptLine): string | null {
	const match = line.text.match(/^(\p{L})\p{L}*\s+(\d+)/u);
	return match ? `${match[1].toUpperCase()}${match[2]}` : null;
}

/** How a seat is named: the model's player name, else the seat id. */
export function seatName(seat: string, players: Record<string, Seat> | undefined): string {
	return players?.[seat]?.name ?? seat;
}

/** The model of a seat, or null for bots and unrated matches. */
export function seatModel(seat: string, players: Record<string, Seat> | undefined): string | null {
	return players?.[seat]?.model ?? null;
}

/**
 * A seat colour hue in degrees, the same for the same model in every match (the seat id
 * when no model is known). Eight hues 45 degrees apart, at equal lightness in CSS.
 */
export function seatHue(key: string): number {
	let hash = 0;
	for (const char of key) hash = (hash * 31 + char.codePointAt(0)!) >>> 0;
	return (hash % 8) * 45 + 20;
}

/** The player's own words of a speech, whisper or thought line, from the event itself. */
export function words(line: TranscriptLine): string | null {
	const data = line.raw?.data;
	if (data && typeof data === 'object' && typeof (data as { text?: unknown }).text === 'string') {
		return (data as { text: string }).text;
	}
	return null;
}

/** The short staged reaction of the stage to a key moment. */
export type Beat =
	'call' | 'reveal' | 'bang' | 'click' | 'allin' | 'win' | 'death' | 'night' | 'end' | 'highlight';

const BEATS: Record<string, Beat> = {
	liar_called: 'call',
	cards_revealed: 'reveal',
	showdown: 'reveal',
	bet_action: 'allin',
	pot_awarded: 'win',
	captain_elected: 'win',
	players_eliminated: 'death',
	player_died: 'death',
	hunter_shot: 'death',
	morning_started: 'death',
	vote_result: 'reveal',
	night_started: 'night',
	match_over: 'end',
	game_over: 'end',
	match_finished: 'end'
};

/**
 * The beat a line asks for, or null. Highlights (importance 3) get one, and so does
 * nightfall; the kind comes from the event type, the words from the line itself.
 */
export function beatOf(line: TranscriptLine): Beat | null {
	const type = String(line.raw?.type ?? '');
	if (type === 'night_started') return 'night';
	if (line.importance < 3) return null;
	if (type === 'trigger_pulled') {
		const data = line.raw?.data as { live?: unknown } | undefined;
		return data?.live === true ? 'bang' : 'click';
	}
	return BEATS[type] ?? 'highlight';
}

/**
 * The beats to play when the shown lines go from `before` (the newest position shown so far)
 * to `lines`: none when the viewer jumped back, or ahead by more than `maxJump` lines that
 * matter (a seek, not watching).
 */
export function newBeats(
	lines: TranscriptLine[],
	before: number,
	maxJump = 12
): { line: TranscriptLine; beat: Beat }[] {
	const fresh = lines.filter((line) => line.seq !== null && line.seq > before);
	const matter = fresh.filter((line) => line.importance > 1 && line.kind !== 'info');
	if (matter.length > maxJump) return [];
	return fresh.flatMap((line) => {
		const beat = beatOf(line);
		return beat ? [{ line, beat }] : [];
	});
}
