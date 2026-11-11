/** The replay list: real-model matches first, then newest first, with filters. */
import type { ReplaySummary } from './api.js';
import { realModels } from './players.js';

export const KINDS = [
	{ id: '', label: 'Real models and bots' },
	{ id: 'real', label: 'Real models' },
	{ id: 'bots', label: 'Bots' }
];

export function filterReplays(
	replays: ReplaySummary[],
	game: string,
	kind: string
): ReplaySummary[] {
	return replays
		.filter((r) => !game || r.game === game)
		.filter((r) => !kind || (kind === 'real') === realModels(r.seats))
		.toSorted(
			(a, b) =>
				Number(realModels(b.seats)) - Number(realModels(a.seats)) ||
				Date.parse(b.finished_at) - Date.parse(a.finished_at)
		);
}
