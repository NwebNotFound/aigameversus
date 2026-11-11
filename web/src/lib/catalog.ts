/** The model picker of the launch form: search, filters and shortcuts over GET /models/catalog. */
import type { CatalogModel } from './api.js';

export interface CatalogFilter {
	/** Words that must all appear in the name, id or vendor (case-insensitive). */
	query: string;
	/** At most this many US dollars per million output tokens; null: any price. */
	maxOutputUsd: number | null;
	reasoning: boolean;
	verifiedOnly: boolean;
	/** At least this many tokens of context; null: any. */
	minContext: number | null;
	/** Only these ids (the favourites); null: every model. */
	only: Set<string> | null;
}

export const NO_FILTER: CatalogFilter = {
	query: '',
	maxOutputUsd: null,
	reasoning: false,
	verifiedOnly: false,
	minContext: null,
	only: null
};

/** The price filters the picker offers, in dollars per million output tokens. */
export const PRICE_STEPS = [
	{ label: 'Any price', usd: null },
	{ label: 'Up to $1 / 1M out', usd: 1 },
	{ label: 'Up to $3 / 1M out', usd: 3 },
	{ label: 'Up to $10 / 1M out', usd: 10 }
] as const;

/** The models that pass the filter, in the catalog's order (verified first). */
export function filterCatalog(models: CatalogModel[], filter: CatalogFilter): CatalogModel[] {
	const words = filter.query.toLowerCase().split(/\s+/).filter(Boolean);
	return models.filter((model) => {
		const text = `${model.name} ${model.id} ${model.openrouter_id} ${model.vendor}`.toLowerCase();
		if (!words.every((word) => text.includes(word))) return false;
		if (filter.maxOutputUsd !== null && model.output_usd_per_mtok > filter.maxOutputUsd)
			return false;
		if (filter.reasoning && !model.reasoning) return false;
		if (filter.verifiedOnly && !model.verified) return false;
		if (filter.minContext !== null && (model.context_length ?? 0) < filter.minContext) return false;
		if (filter.only && !filter.only.has(model.id)) return false;
		return true;
	});
}

/**
 * "Fill with cheap models": the cheapest verified models that cost something,
 * one per seat, different models first (then round again). Free models are left
 * out: their providers limit them hard and a match stalls on their limits.
 */
export function cheapSeats(models: CatalogModel[], seats: number): string[] {
	const cheap = models
		.filter((model) => model.verified && !model.free)
		.toSorted(
			(a, b) =>
				a.input_usd_per_mtok +
				a.output_usd_per_mtok -
				(b.input_usd_per_mtok + b.output_usd_per_mtok)
		);
	if (!cheap.length) return [];
	return Array.from({ length: seats }, (_, i) => cheap[i % cheap.length].id);
}

/** "$0.040 / $0.078": a price per million tokens in and out, short. */
export function priceLabel(model: CatalogModel): string {
	const usd = (value: number) =>
		value === 0 ? '$0' : `$${value < 1 ? value.toFixed(3) : value.toFixed(2)}`;
	return `${usd(model.input_usd_per_mtok)} / ${usd(model.output_usd_per_mtok)}`;
}

const FAVOURITES_KEY = 'aigameversus:favourite-models';

/** The favourite model ids of this browser. */
export function loadFavourites(storage: Pick<Storage, 'getItem'> | undefined): Set<string> {
	try {
		const raw = storage?.getItem(FAVOURITES_KEY);
		const ids = raw ? JSON.parse(raw) : [];
		return new Set(Array.isArray(ids) ? ids.filter((id) => typeof id === 'string') : []);
	} catch {
		return new Set();
	}
}

export function saveFavourites(
	storage: Pick<Storage, 'setItem'> | undefined,
	favourites: Set<string>
): void {
	try {
		storage?.setItem(FAVOURITES_KEY, JSON.stringify([...favourites].sort()));
	} catch {
		// A browser without storage simply forgets them.
	}
}
