export interface NavItem {
	href: string;
	label: string;
	soon?: boolean;
}

export const NAV: NavItem[] = [
	{ href: '/', label: 'Home' },
	{ href: '/new', label: 'New match', soon: true },
	{ href: '/leaderboard', label: 'Leaderboard', soon: true },
	{ href: '/replays', label: 'Replays', soon: true }
];
