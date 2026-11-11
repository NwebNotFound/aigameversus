/**
 * The watch screen (live view and replay): viewer modes, what reaches the browser in
 * each, and how transcript lines map onto the replay timeline.
 *
 * Text comes only from the transcript (`arena/transcript`); nothing here words an event.
 */
import type { MatchEvent, RecordSeat, Seat, SetupOptions, TranscriptLine } from './api.js';

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
	const info = players?.[seat];
	return info?.display ?? info?.name ?? seat;
}

/** "p3" as 3, for the small seat badge: the only place a seat id is shown. */
export function seatNumber(seat: string): string {
	return seat.replace(/^p/, '');
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

export interface Placement {
	player: string;
	rank: number;
}

/** How a match ended, for the result card. The words come from the transcript's lines. */
export type Result =
	| {
			kind: 'team';
			/** The transcript's line about the end, e.g. "Game over: the werewolves win". */
			headline: string;
			winners: string[];
			others: string[];
	  }
	| { kind: 'ranks'; headline: string; ranks: { rank: number; seats: string[] }[] };

/**
 * The result of a finished match from its placements and the transcript. A game whose end
 * names a winning side (Werewolf's `game_over`) is a team result; every other game is ranked.
 */
export function resultOf(placements: Placement[] | null, lines: TranscriptLine[]): Result | null {
	if (!placements || placements.length === 0) return null;
	const end = lines.findLast((line) =>
		['game_over', 'match_over'].includes(String(line.raw?.type))
	);
	const data = (end?.raw?.data ?? {}) as { winner?: unknown; winners?: unknown };
	const headline = end?.text ?? '';
	if (typeof data.winner === 'string' && Array.isArray(data.winners)) {
		const winners = data.winners.filter((p): p is string => typeof p === 'string');
		const others = placements.map((p) => p.player).filter((p) => !winners.includes(p));
		return { kind: 'team', headline, winners, others };
	}
	const byRank = new Map<number, string[]>();
	for (const { player, rank } of [...placements].sort((a, b) => a.rank - b.rank)) {
		byRank.set(rank, [...(byRank.get(rank) ?? []), player]);
	}
	return {
		kind: 'ranks',
		headline,
		ranks: [...byRank].map(([rank, seats]) => ({ rank, seats }))
	};
}

/** "1st", "2nd", "3rd", "4th" … for ranks on the card. */
export function ordinal(rank: number): string {
	const tens = rank % 100;
	if (tens >= 11 && tens <= 13) return `${rank}th`;
	return `${rank}${['th', 'st', 'nd', 'rd'][rank % 10] ?? 'th'}`;
}

export interface ShownHand {
	player: string;
	cards: string[];
	/** The hand's kind as the game names it: "two_pair" reads "two pair". */
	hand: string;
	/** Chips this player won from the pots that follow the showdown. */
	won: number;
}

/**
 * The hands of a showdown line and what each won, from the pot lines right after it, for
 * a row per player instead of one long sentence.
 */
export function showdownHands(lines: TranscriptLine[], index: number): ShownHand[] {
	const data = lines[index]?.raw?.data as { hands?: unknown } | undefined;
	if (!Array.isArray(data?.hands)) return [];
	const won = new Map<string, number>();
	for (const line of lines.slice(index + 1)) {
		if (line.raw?.type !== 'pot_awarded') break;
		const shares = (line.raw.data as { shares?: Record<string, number> }).shares ?? {};
		for (const [player, amount] of Object.entries(shares))
			won.set(player, (won.get(player) ?? 0) + amount);
	}
	return data.hands.flatMap((entry) => {
		const { player, cards, hand } = entry as { player?: unknown; cards?: unknown; hand?: unknown };
		if (typeof player !== 'string' || !Array.isArray(cards)) return [];
		return [
			{
				player,
				cards: cards.map(String),
				hand: typeof hand === 'string' ? hand.replaceAll('_', ' ') : '',
				won: won.get(player) ?? 0
			}
		];
	});
}

/**
 * Who sits in each seat, from every source the page has. The match record's seats come
 * first (they exist for running and finished matches), then the transcript's players,
 * then the roster for vendor and price. A model seat is never shown as a bot.
 */
export function mergeSeats(
	order: string[],
	record: Record<string, RecordSeat> | undefined,
	transcript: Record<string, Seat> | undefined,
	roster: SetupOptions['models'] = []
): Record<string, Seat> {
	const byId = new Map(roster.map((m) => [m.id, m]));
	const merged: Record<string, Seat> = Object.fromEntries(
		order.map((seat) => {
			const stored = record?.[seat];
			const told = transcript?.[seat];
			const model = stored?.model_id ?? told?.model ?? null;
			const known = model ? byId.get(model) : undefined;
			const kind: 'model' | 'bot' | undefined =
				stored?.kind ?? (model ? 'model' : told?.name ? 'bot' : undefined);
			return [
				seat,
				{
					display: told?.display ?? stored?.display ?? null,
					name: told?.name ?? stored?.name ?? null,
					model,
					kind,
					vendor: known?.model.includes('/') ? known.model.split('/')[0] : null,
					personality: stored?.personality ?? null,
					price: known
						? { input: known.input_usd_per_mtok, output: known.output_usd_per_mtok }
						: null
				}
			];
		})
	);
	return withDisplayNames(order, merged);
}

/**
 * The display name of every seat (Lead's rule), unless the API already gave one: a model
 * by its short name, with "#2" for the second seat of the same model; a bot "Bot 1",
 * "Bot 2" in seat order. Unique within the match; the seat id is never the name.
 */
export function withDisplayNames(
	order: string[],
	seats: Record<string, Seat>
): Record<string, Seat> {
	const seen = new Map<string, number>();
	let bots = 0;
	for (const seat of order) {
		const info = seats[seat];
		if (!info || info.display) continue;
		if (info.kind === 'bot' || (!info.model && /^Random Bot/i.test(info.name ?? ''))) {
			bots += 1;
			info.display = `Bot ${bots}`;
			continue;
		}
		const base = info.model
			? info.name && info.name !== info.model
				? info.name
				: info.model
			: info.name;
		if (!base) continue;
		const count = (seen.get(base) ?? 0) + 1;
		seen.set(base, count);
		info.display = count === 1 ? base : `${base} #${count}`;
	}
	return seats;
}

/**
 * A transcript sentence with every seat id ("p3", also inside "Random Bot p3 (random-bot)")
 * replaced by that seat's display name. Until the transcript names players itself, this is
 * how a sentence reads; it adds no words of its own.
 */
export function namedText(text: string, players: Record<string, Seat> | undefined): string {
	if (!players) return text;
	return text.replace(/(?:Random Bot )?\b(p\d+)\b(?: \(random-bot\))?/g, (whole, seat: string) =>
		players[seat] ? seatName(seat, players) : whole
	);
}

/** The colour key of a seat: its vendor, so one company's models share a family of hues. */
export function colourKey(seat: string, players: Record<string, Seat> | undefined): string {
	const info = players?.[seat];
	return info?.vendor ?? info?.model ?? seat;
}

/** The lines with every seat id in their text and detail replaced by display names. */
export function namedLines(
	lines: TranscriptLine[],
	players: Record<string, Seat> | undefined
): TranscriptLine[] {
	if (!players) return lines;
	return lines.map((line) => ({
		...line,
		text: namedText(line.text, players),
		detail: line.detail === null ? null : namedText(line.detail, players)
	}));
}

/**
 * The small line under a seat's name: the model id when the name does not already say it,
 * and the vendor; "Random Bot" for a bot. Null when there is nothing to add.
 */
export function seatSub(seat: string, players: Record<string, Seat> | undefined): string | null {
	const info = players?.[seat];
	const shown = seatName(seat, players).replace(/ #\d+$/, '');
	const model = info?.model && info.model !== shown ? info.model : null;
	const line = [model, info?.vendor].filter(Boolean).join(' · ');
	return line || (info?.kind === 'bot' ? 'Random Bot' : null);
}
