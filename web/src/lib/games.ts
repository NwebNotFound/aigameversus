/** The four games of the first build, shown as cards on the home page. */
export interface GameCard {
	/** Plugin id, as in `games/<id>/`. */
	id: string;
	name: string;
	/** One line on what the game tests. */
	tagline: string;
	players: string;
	/** Card highlight colour (CSS). */
	accent: string;
}

export const GAMES: GameCard[] = [
	{
		id: 'liars_deck',
		name: "Liar's Deck",
		tagline: 'Bluff with face-down cards, call the lie, survive the revolver.',
		players: '2–4 players',
		accent: '#f0b35a'
	},
	{
		id: 'poker',
		name: 'Poker',
		tagline: "No-Limit Texas Hold'em with table talk.",
		players: '2–6 players',
		accent: '#7ad69a'
	},
	{
		id: 'werewolf',
		name: 'Werewolf',
		tagline: 'Hidden roles: lie, deduce and persuade the village.',
		players: '6–16 players',
		accent: '#ff7a7a'
	},
	{
		id: 'civ',
		name: 'Throne of Tokens',
		tagline: 'Economy, war and broken alliances on a hex map.',
		players: '4–6 nations',
		accent: '#7fb8ff'
	}
];

/** Display names for game ids that have no card, such as the High Card reference game. */
const OTHER_NAMES: Record<string, string> = { toy: 'High Card' };

/** A readable name for a game id; the id itself when the game is unknown. */
export function gameName(id: string): string {
	return GAMES.find((game) => game.id === id)?.name ?? OTHER_NAMES[id] ?? id;
}
