/**
 * Match events as sentences people read, in English or German.
 *
 * `eventText` returns null for an event it does not know; the feed then shows
 * the raw line. Player ids are shown as they are (p1, p2, ...).
 */
import type { MatchEvent } from './api.js';

export type Lang = 'en' | 'de';

type Data = Record<string, unknown>;
type Phrase = (d: Data, lang: Lang) => string;

const str = (value: unknown) => String(value ?? '');
const list = (value: unknown, lang: Lang) => {
	const items = Array.isArray(value) ? value.map(str) : [];
	if (items.length <= 1) return items.join('');
	const and = lang === 'de' ? ' und ' : ' and ';
	return items.slice(0, -1).join(', ') + and + items.at(-1);
};
const t = (lang: Lang, en: string, de: string) => (lang === 'de' ? de : en);
const humanize = (id: unknown) => str(id).replaceAll('_', ' ');

/** 1 -> "1st" / "1."; shared ranks are written the same. */
export function ordinal(rank: number, lang: Lang): string {
	if (lang === 'de') return `${rank}.`;
	const tens = rank % 100;
	const suffix =
		tens >= 11 && tens <= 13
			? 'th'
			: (({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[rank % 10] ?? 'th');
	return `${rank}${suffix}`;
}

/** The final placements as one line: "1st p4 · 2nd p2, p3 · 4th p1". */
export function placementsText(placements: unknown, lang: Lang): string {
	const byRank = new Map<number, string[]>();
	for (const p of Array.isArray(placements) ? placements : []) {
		const { player, rank } = (p ?? {}) as { player?: unknown; rank?: unknown };
		if (typeof rank !== 'number') continue;
		byRank.set(rank, [...(byRank.get(rank) ?? []), str(player)]);
	}
	return [...byRank.entries()]
		.sort(([a], [b]) => a - b)
		.map(([rank, players]) => `${ordinal(rank, lang)} ${players.join(', ')}`)
		.join(' · ');
}

const ENGINE: Record<string, Phrase> = {
	match_started: (d, l) =>
		t(l, `The match starts: ${list(d.players, l)}.`, `Die Partie beginnt: ${list(d.players, l)}.`),
	match_finished: (d, l) =>
		t(
			l,
			`Result: ${placementsText(d.placements, l)}`,
			`Ergebnis: ${placementsText(d.placements, l)}`
		),
	match_paused: (_, l) => t(l, 'The match is paused.', 'Die Partie ist pausiert.'),
	match_resumed: (_, l) => t(l, 'The match goes on.', 'Die Partie geht weiter.'),
	turn_limit_reached: (_, l) =>
		t(
			l,
			'The match reached its turn limit and stops.',
			'Die Partie hat ihr Zuglimit erreicht und endet.'
		),
	action_accepted: (d, l) =>
		t(
			l,
			`${str(d.player)} plays ${humanize(d.tool)}.`,
			`${str(d.player)} spielt ${humanize(d.tool)}.`
		),
	action_rejected: (d, l) =>
		t(
			l,
			`${str(d.player)} tried ${humanize(d.tool)}; refused: ${str(d.error)}`,
			`${str(d.player)} versuchte ${humanize(d.tool)}; abgelehnt: ${str(d.error)}`
		),
	action_fallback: (d, l) =>
		t(
			l,
			`${str(d.player)} gave no valid move; a random one was played.`,
			`${str(d.player)} gab keinen gültigen Zug; ein zufälliger wurde gespielt.`
		),
	agent_failed: (d, l) =>
		t(
			l,
			`${str(d.player)} stopped answering; a random bot plays the seat.`,
			`${str(d.player)} antwortet nicht mehr; ein Zufallsbot spielt den Platz.`
		)
};

const LIARS_DECK: Record<string, Phrase> = {
	round_started: (d, l) =>
		t(
			l,
			`Round ${str(d.round)} starts. Table card: ${humanize(d.table_card)}; ${str(d.starter)} begins.`,
			`Runde ${str(d.round)} beginnt. Tischkarte: ${humanize(d.table_card)}; ${str(d.starter)} fängt an.`
		),
	hand_dealt: (d, l) =>
		t(
			l,
			`${str(d.player)} is dealt ${list(d.cards, l)}.`,
			`${str(d.player)} bekommt ${list(d.cards, l)}.`
		),
	revolver_loaded: (d, l) =>
		t(
			l,
			`${str(d.player)}'s revolver is loaded.`,
			`Der Revolver von ${str(d.player)} ist geladen.`
		),
	cards_played: (d, l) =>
		t(
			l,
			`${str(d.player)} plays ${str(d.count)} card${d.count === 1 ? '' : 's'} face down.`,
			`${str(d.player)} legt ${str(d.count)} Karte${d.count === 1 ? '' : 'n'} verdeckt.`
		),
	cards_hidden: (d, l) =>
		t(
			l,
			`(${str(d.player)} really played ${list(d.cards, l)}.)`,
			`(${str(d.player)} hat wirklich ${list(d.cards, l)} gelegt.)`
		),
	turn_passed: (d, l) =>
		d.auto_call
			? t(
					l,
					`${str(d.player)} has no cards left and must call.`,
					`${str(d.player)} hat keine Karten mehr und muss aufdecken.`
				)
			: t(l, `${str(d.player)} lets it pass.`, `${str(d.player)} lässt es durchgehen.`),
	liar_called: (d, l) =>
		d.automatic
			? t(
					l,
					`The cards of ${str(d.target)} are turned over.`,
					`Die Karten von ${str(d.target)} werden aufgedeckt.`
				)
			: t(
					l,
					`${str(d.caller)} calls ${str(d.target)} a liar!`,
					`${str(d.caller)} nennt ${str(d.target)} einen Lügner!`
				),
	cards_revealed: (d, l) =>
		d.honest
			? t(
					l,
					`The cards of ${str(d.player)} are true: ${list(d.cards, l)}.`,
					`Die Karten von ${str(d.player)} stimmen: ${list(d.cards, l)}.`
				)
			: t(
					l,
					`The cards of ${str(d.player)} show a bluff: ${list(d.cards, l)}.`,
					`Die Karten von ${str(d.player)} zeigen einen Bluff: ${list(d.cards, l)}.`
				),
	shooters_chosen: (d, l) =>
		t(l, `${list(d.players, l)} must pull the trigger.`, `${list(d.players, l)} muss abdrücken.`),
	trigger_pulled: (d, l) =>
		d.live
			? t(l, `${str(d.player)} pulls the trigger: BANG.`, `${str(d.player)} drückt ab: PENG.`)
			: t(
					l,
					`${str(d.player)} pulls the trigger: click. Pull ${str(d.pull)}.`,
					`${str(d.player)} drückt ab: klick. Versuch ${str(d.pull)}.`
				),
	players_eliminated: (d, l) =>
		t(l, `${list(d.players, l)} is out.`, `${list(d.players, l)} ist raus.`),
	round_ended: (d, l) => t(l, `Round ${str(d.round)} ends.`, `Runde ${str(d.round)} endet.`),
	match_over: (d, l) =>
		t(l, `${str(d.winner)} survives and wins.`, `${str(d.winner)} überlebt und gewinnt.`)
};

const BET: Record<string, [string, string]> = {
	fold: ['folds', 'steigt aus'],
	check: ['checks', 'schiebt'],
	call: ['calls', 'geht mit'],
	raise: ['raises', 'erhöht'],
	all_in: ['goes all in', 'geht all-in']
};

const STREET: Record<string, [string, string]> = {
	preflop: ['Pre-flop', 'Pre-Flop'],
	flop: ['The flop', 'Der Flop'],
	turn: ['The turn', 'Der Turn'],
	river: ['The river', 'Der River']
};

const POKER: Record<string, Phrase> = {
	hand_started: (d, l) =>
		t(
			l,
			`Hand ${str(d.hand)}: ${str(d.button)} has the button.`,
			`Hand ${str(d.hand)}: ${str(d.button)} hat den Button.`
		),
	deck_shuffled: (_, l) => t(l, 'The deck is shuffled.', 'Das Deck wird gemischt.'),
	hole_dealt: (d, l) =>
		t(
			l,
			`${str(d.player)} holds ${list(d.cards, l)}.`,
			`${str(d.player)} hält ${list(d.cards, l)}.`
		),
	blind_posted: (d, l) =>
		d.kind === 'small'
			? t(
					l,
					`${str(d.player)} posts the small blind of ${str(d.amount)}.`,
					`${str(d.player)} setzt den Small Blind von ${str(d.amount)}.`
				)
			: t(
					l,
					`${str(d.player)} posts the big blind of ${str(d.amount)}.`,
					`${str(d.player)} setzt den Big Blind von ${str(d.amount)}.`
				),
	street_started: (d, l) => {
		const [en, de] = STREET[str(d.street)] ?? [humanize(d.street), humanize(d.street)];
		const cards = Array.isArray(d.cards) && d.cards.length ? `: ${list(d.cards, l)}` : '';
		return t(l, `${en}${cards}.`, `${de}${cards}.`);
	},
	bet_action: (d, l) => {
		const [en, de] = BET[str(d.kind)] ?? [humanize(d.kind), humanize(d.kind)];
		const to = ['raise', 'all_in'].includes(str(d.kind))
			? t(l, ` to ${str(d.to)}`, ` auf ${str(d.to)}`)
			: '';
		return `${str(d.player)} ${t(l, en, de)}${to}.`;
	},
	showdown: (d, l) => {
		const hands = (Array.isArray(d.hands) ? d.hands : []) as Data[];
		if (!hands.length) return '';
		const shown = hands
			.map((h) => `${str(h.player)} ${list(h.cards, l)} (${humanize(h.hand)})`)
			.join('; ');
		return t(l, `Showdown: ${shown}.`, `Showdown: ${shown}.`);
	},
	pot_awarded: (d, l) => {
		const shares = Object.entries((d.shares ?? {}) as Record<string, number>).filter(
			([, chips]) => chips > 0
		);
		if (!shares.length) return '';
		const won = shares.map(([player, chips]) => `${player} ${chips}`).join(', ');
		return t(
			l,
			`Pot of ${str(d.amount)} won: ${won}.`,
			`Pot von ${str(d.amount)} gewonnen: ${won}.`
		);
	},
	hand_ended: (d, l) => t(l, `Hand ${str(d.hand)} is over.`, `Hand ${str(d.hand)} ist vorbei.`),
	players_eliminated: (d, l) =>
		t(l, `${list(d.players, l)} is out of chips.`, `${list(d.players, l)} hat keine Chips mehr.`),
	match_over: (d, l) =>
		t(l, `${str(d.winner)} wins the tournament.`, `${str(d.winner)} gewinnt das Turnier.`)
};

const CAUSE: Record<string, [string, string]> = {
	wolves: ['killed by the wolves', 'von den Wölfen getötet'],
	poison: ['poisoned', 'vergiftet'],
	executed: ['executed by the village', 'vom Dorf hingerichtet'],
	hunter: ['shot by the hunter', 'vom Jäger erschossen'],
	grief: ['died of grief', 'starb vor Kummer'],
	caught_spying: ['caught spying by the wolves', 'von den Wölfen beim Spionieren erwischt'],
	scapegoat: ['the scapegoat of a tied vote', 'Sündenbock einer Patt-Abstimmung'],
	white_wolf: ['killed by the white werewolf', 'vom Weißen Werwolf getötet']
};

const WEREWOLF: Record<string, Phrase> = {
	roles_dealt: (_, l) => t(l, 'The roles are dealt.', 'Die Rollen werden verteilt.'),
	role_assigned: (d, l) =>
		t(
			l,
			`${str(d.player)} is the ${humanize(d.role)}.`,
			`${str(d.player)} ist ${humanize(d.role)}.`
		),
	pack_revealed: (d, l) =>
		t(l, `The pack: ${list(d.wolves, l)}.`, `Das Rudel: ${list(d.wolves, l)}.`),
	night_started: (d, l) =>
		t(l, `Night ${str(d.night)} falls.`, `Nacht ${str(d.night)} bricht herein.`),
	morning_started: (d, l) => {
		const dead = Array.isArray(d.deaths) && d.deaths.length;
		return dead
			? t(
					l,
					`Morning. The village finds ${list(d.deaths, l)} dead.`,
					`Morgen. Das Dorf findet ${list(d.deaths, l)} tot.`
				)
			: t(l, 'Morning. Nobody died tonight.', 'Morgen. Heute Nacht ist niemand gestorben.');
	},
	day_started: (d, l) =>
		t(l, `Day ${str(d.day)}: the village talks.`, `Tag ${str(d.day)}: das Dorf berät.`),
	player_died: (d, l) => {
		const [en, de] = CAUSE[str(d.cause)] ?? [humanize(d.cause), humanize(d.cause)];
		return t(
			l,
			`${str(d.player)} is dead (${en}); they were the ${humanize(d.role)}.`,
			`${str(d.player)} ist tot (${de}); Rolle: ${humanize(d.role)}.`
		);
	},
	vote_cast: (d, l) =>
		d.target === null
			? t(l, `${str(d.player)} votes for nobody.`, `${str(d.player)} stimmt für niemanden.`)
			: t(
					l,
					`${str(d.player)} votes against ${str(d.target)}.`,
					`${str(d.player)} stimmt gegen ${str(d.target)}.`
				),
	vote_result: (d, l) =>
		d.executed
			? t(
					l,
					`The village decides: ${str(d.executed)} is executed.`,
					`Das Dorf entscheidet: ${str(d.executed)} wird hingerichtet.`
				)
			: t(
					l,
					'The village cannot agree; nobody is executed.',
					'Das Dorf wird sich nicht einig; niemand wird hingerichtet.'
				),
	captain_vote: (d, l) =>
		t(
			l,
			`${str(d.player)} wants ${str(d.target)} as captain.`,
			`${str(d.player)} will ${str(d.target)} als Hauptmann.`
		),
	captain_elected: (d, l) =>
		t(l, `${str(d.player)} is elected captain.`, `${str(d.player)} wird zum Hauptmann gewählt.`),
	captain_passed: (d, l) =>
		t(
			l,
			`${str(d.from)} hands the captaincy to ${str(d.to)}.`,
			`${str(d.from)} übergibt das Hauptmannsamt an ${str(d.to)}.`
		),
	wolf_vote: (d, l) =>
		t(
			l,
			`${str(d.player)} wants to hunt ${str(d.target)}.`,
			`${str(d.player)} will ${str(d.target)} jagen.`
		),
	seer_inspected: (d, l) =>
		t(
			l,
			`The seer ${str(d.player)} sees that ${str(d.target)} is the ${humanize(d.role)}.`,
			`Die Seherin ${str(d.player)} sieht: ${str(d.target)} ist ${humanize(d.role)}.`
		),
	witch_acted: (d, l) => {
		const parts = [
			d.healed ? t(l, `heals ${str(d.healed)}`, `heilt ${str(d.healed)}`) : null,
			d.poisoned ? t(l, `poisons ${str(d.poisoned)}`, `vergiftet ${str(d.poisoned)}`) : null
		].filter(Boolean);
		return parts.length
			? t(
					l,
					`The witch ${str(d.player)} ${parts.join(' and ')}.`,
					`Die Hexe ${str(d.player)} ${parts.join(' und ')}.`
				)
			: t(l, `The witch ${str(d.player)} does nothing.`, `Die Hexe ${str(d.player)} tut nichts.`);
	},
	protected: (d, l) =>
		t(
			l,
			`${str(d.player)} protects ${str(d.target)} tonight.`,
			`${str(d.player)} beschützt heute Nacht ${str(d.target)}.`
		),
	lovers_linked: (d, l) =>
		t(
			l,
			`Cupid ${str(d.player)} makes ${list(d.lovers, l)} fall in love.`,
			`Amor ${str(d.player)} lässt ${list(d.lovers, l)} sich verlieben.`
		),
	love_revealed: (d, l) =>
		t(l, `${list(d.lovers, l)} are in love.`, `${list(d.lovers, l)} sind verliebt.`),
	hunter_shot: (d, l) =>
		t(
			l,
			`The hunter ${str(d.player)} shoots ${str(d.target)}.`,
			`Der Jäger ${str(d.player)} erschießt ${str(d.target)}.`
		),
	raven_chose: (d, l) =>
		t(
			l,
			`The raven ${str(d.player)} marks ${str(d.target)}.`,
			`Der Rabe ${str(d.player)} markiert ${str(d.target)}.`
		),
	raven_mark_announced: (d, l) =>
		t(
			l,
			`The raven has marked ${str(d.target)}: two votes against them today.`,
			`Der Rabe hat ${str(d.target)} markiert: heute zwei Stimmen gegen sie.`
		),
	idiot_revealed: (d, l) =>
		t(
			l,
			`${str(d.player)} is the village idiot and is spared, but loses the vote.`,
			`${str(d.player)} ist der Dorfdepp, bleibt am Leben und verliert die Stimme.`
		),
	elder_survived: (d, l) =>
		t(
			l,
			`The elder ${str(d.player)} survives the attack.`,
			`Der Dorfälteste ${str(d.player)} überlebt den Angriff.`
		),
	model_chosen: (d, l) =>
		t(
			l,
			`The wild child ${str(d.player)} picks ${str(d.model)} as role model.`,
			`Das wilde Kind ${str(d.player)} wählt ${str(d.model)} als Vorbild.`
		),
	joined_pack: (d, l) =>
		t(l, `${str(d.player)} joins the pack.`, `${str(d.player)} schließt sich dem Rudel an.`),
	infection_chosen: (d, l) =>
		t(
			l,
			`The prime wolf ${str(d.player)} chooses to infect ${str(d.target)}.`,
			`Der Urwolf ${str(d.player)} will ${str(d.target)} infizieren.`
		),
	white_wolf_chose: (d, l) =>
		d.target
			? t(
					l,
					`The white werewolf ${str(d.player)} turns on ${str(d.target)}.`,
					`Der Weiße Werwolf ${str(d.player)} wendet sich gegen ${str(d.target)}.`
				)
			: t(
					l,
					`The white werewolf ${str(d.player)} spares the pack.`,
					`Der Weiße Werwolf ${str(d.player)} verschont das Rudel.`
				),
	wolf_talked: (d, l) =>
		t(l, `${str(d.player)} whispers to the pack.`, `${str(d.player)} flüstert mit dem Rudel.`),
	lover_talked: (d, l) =>
		t(
			l,
			`${str(d.player)} whispers to their lover.`,
			`${str(d.player)} flüstert mit dem Geliebten.`
		),
	step_done: (d, l) =>
		t(l, `${str(d.player)} is done for tonight.`, `${str(d.player)} ist für heute Nacht fertig.`),
	game_over: (d, l) => {
		const side = str(d.winner);
		const en = { village: 'The village wins', wolves: 'The wolves win', lovers: 'The lovers win' }[
			side
		];
		const de = {
			village: 'Das Dorf gewinnt',
			wolves: 'Die Wölfe gewinnen',
			lovers: 'Die Liebenden gewinnen'
		}[side];
		return t(
			l,
			`${en ?? `${humanize(side)} wins`}: ${list(d.winners, l)}.`,
			`${de ?? `${humanize(side)} gewinnt`}: ${list(d.winners, l)}.`
		);
	}
};

const TOY: Record<string, Phrase> = {
	hand_dealt: LIARS_DECK.hand_dealt,
	card_played: (d, l) =>
		t(
			l,
			`${str(d.player)} plays a ${str(d.card)}.`,
			`${str(d.player)} spielt eine ${str(d.card)}.`
		),
	trick_won: (d, l) =>
		t(l, `${str(d.player)} wins the trick.`, `${str(d.player)} gewinnt den Stich.`)
};

const GAMES: Record<string, Record<string, Phrase>> = {
	liars_deck: LIARS_DECK,
	poker: POKER,
	werewolf: WEREWOLF,
	toy: TOY
};

/** The event as a sentence, or null when there is none for it (the feed then shows it raw). */
export function eventText(game: string, event: MatchEvent, lang: Lang): string | null {
	const phrase = event.source === 'engine' ? ENGINE[event.type] : GAMES[game]?.[event.type];
	if (!phrase) return null;
	try {
		const text = phrase(event.data, lang);
		return text || null;
	} catch {
		return null; // data of an unexpected shape: the raw line is better than nothing
	}
}

/** The language of a match's text: its `language` setting, English otherwise. */
export function matchLang(settings: Record<string, unknown> | undefined): Lang {
	return settings?.language === 'de' ? 'de' : 'en';
}
