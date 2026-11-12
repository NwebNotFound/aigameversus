import type { ApiResult, ArenaClient, Transcript } from '../api.js';
import { publicTranscript, withRepairMarks } from './redact.js';

/**
 * The transcript as a view may see it. Spoiler-free: the arena's public lines, with only the
 * marks of repaired moves added from the spectator lines (withRepairMarks); those lines are
 * read here on the server and never sent on.
 */
export async function transcriptFor(
	arena: ArenaClient,
	id: string,
	spectator: boolean,
	lang: 'en' | 'de'
): Promise<ApiResult<Transcript>> {
	if (spectator) return arena.transcript(id, true, lang);
	const [open, full] = await Promise.all([
		arena.transcript(id, false, lang),
		arena.transcript(id, true, lang)
	]);
	if (open.state !== 'ok') return open;
	const data = publicTranscript(open.data);
	return {
		state: 'ok',
		data: full.state === 'ok' ? withRepairMarks(data, full.data.lines) : data
	};
}
