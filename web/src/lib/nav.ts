export interface NavItem {
	href: string;
	label: string;
	soon?: boolean;
}

export const NAV: NavItem[] = [
	{ href: '/', label: 'Home' },
	{ href: '/matches/new', label: 'New match' },
	{ href: '/leaderboard', label: 'Leaderboard' },
	{ href: '/replays', label: 'Replays', soon: true }
];
