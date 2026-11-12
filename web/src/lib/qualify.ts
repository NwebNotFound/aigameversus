import type { NewQualification, QualificationQuote } from './api.js';

/** The games with a core qualification manifest (arena/qualify/manifest.py). */
export const QUALIFY_GAMES = ['liars_deck', 'poker'] as const;

export type Repair = 'off' | 'v1';

export function repairOf(value: string | null): Repair {
	return value === 'v1' ? 'v1' : 'off';
}

/** A cap in euros, for the form: the micro-euros rounded up to the next cent. */
export function capEuros(micro: number): number {
	return Math.ceil(micro / 10_000) / 100;
}

export type QualifyForm = { ok: true; job: NewQualification } | { ok: false; error: string };

/**
 * A "Test this model" click, checked before it is sent: a game with core cases, the spend
 * confirmed, and a cap above 0 that holds the job's worst case and stays within the arena's
 * per-match cap. A job never shrinks to fit a smaller cap (research/QUALIFY.md).
 */
export function parseQualifyForm(
	form: FormData,
	model: string,
	quote: QualificationQuote
): QualifyForm {
	const game = String(form.get('game') ?? '');
	if (!(QUALIFY_GAMES as readonly string[]).includes(game) || game !== quote.game) {
		return { ok: false, error: 'Choose a game that has qualification cases.' };
	}
	if (form.get('confirm_spend') === null) {
		return { ok: false, error: 'A test spends money: tick the box to start it.' };
	}
	const euros = Number(String(form.get('max_eur') ?? '').trim());
	if (!Number.isFinite(euros) || euros <= 0) {
		return { ok: false, error: 'The spend limit is a number of euros above 0.' };
	}
	if (euros * 1_000_000 > quote.max_cap_micro_eur) {
		return {
			ok: false,
			error: `The spend limit is at most the per-match cap of ${capEuros(quote.max_cap_micro_eur).toFixed(2)} €.`
		};
	}
	if (Math.round(euros * 1_000_000) < quote.reserved_micro_eur) {
		return {
			ok: false,
			error: `This test may cost up to ${capEuros(quote.reserved_micro_eur).toFixed(2)} €: raise the limit to at least that to run it.`
		};
	}
	return {
		ok: true,
		job: {
			model,
			game,
			answer_repair: repairOf(String(form.get('answer_repair') ?? '')),
			confirm_spend: true,
			max_eur: euros
		}
	};
}
