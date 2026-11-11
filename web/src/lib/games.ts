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
		tagline: 'Bluff, call the lie, survive the risk.',
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
		tagline: 'Lie, deduce and persuade the village.',
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
