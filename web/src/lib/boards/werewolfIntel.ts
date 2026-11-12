/**
 * What the table said about itself, for the Werewolf panel under the circle: who claimed
 * which role, and who suspects whom. Read from the match analytics (docs/METRICS.md,
 * `claims`, `accusations`), cut at the moment on screen.
 */

export interface Claim {
	seq: number;
	player: string;
	role: string;
	phase?: { kind: string; number: number } | null;
	changed_from: string | null;
	counterclaimed_by: string[];
	disproved: boolean;
	true_role: string | null;
	/** Spoilers: true or false. Spoiler-free: true once a death revealed it, else null. */
	lie: boolean | null;
	heuristic?: boolean;
}

export interface Accusation {
	seq: number;
	day?: number;
	by: string;
	target: string;
	source: 'vote' | 'speech';
	heuristic?: boolean;
}

/** Each player's claims up to the event at `lastSeq`, in the order they were made. */
export function claimsUpTo(claims: Claim[], lastSeq: number | null): Map<string, Claim[]> {
	const out = new Map<string, Claim[]>();
	for (const claim of claims) {
		if (lastSeq !== null && claim.seq > lastSeq) continue;
		const mine = out.get(claim.player) ?? [];
		mine.push(claim);
		out.set(claim.player, mine);
	}
	return out;
}

export interface Cell {
	/** Sentences that accused the target (heuristic). */
	speech: number;
	/** Votes cast on the target. */
	votes: number;
}

/**
 * Who suspects whom up to the moment on screen: per accuser and target the accusing
 * sentences and the votes. `max` is the largest cell, for the shading.
 */
export function suspicion(
	accusations: Accusation[],
	lastSeq: number | null
): { cells: Map<string, Map<string, Cell>>; max: number } {
	const cells = new Map<string, Map<string, Cell>>();
	let max = 0;
	for (const a of accusations) {
		if (lastSeq !== null && a.seq > lastSeq) continue;
		if (a.by === a.target) continue;
		const row = cells.get(a.by) ?? new Map<string, Cell>();
		const cell = row.get(a.target) ?? { speech: 0, votes: 0 };
		if (a.source === 'vote') cell.votes += 1;
		else cell.speech += 1;
		row.set(a.target, cell);
		cells.set(a.by, row);
		max = Math.max(max, cell.speech + cell.votes);
	}
	return { cells, max };
}

/** Of everyone, the player the table suspects most so far (votes and speech), if any. */
export function mostSuspected(accusations: Accusation[], lastSeq: number | null): string | null {
	const totals = new Map<string, number>();
	for (const a of accusations)
		if ((lastSeq === null || a.seq <= lastSeq) && a.by !== a.target)
			totals.set(a.target, (totals.get(a.target) ?? 0) + 1);
	let best: string | null = null;
	let most = 0;
	for (const [target, n] of totals)
		if (n > most) [best, most] = [target, n];
		else if (n === most) best = null; // a tie names nobody
	return best;
}
