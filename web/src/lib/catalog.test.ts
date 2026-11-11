import { describe, expect, it } from 'vitest';
import type { CatalogModel } from './api.js';
import {
	cheapSeats,
	filterCatalog,
	loadFavourites,
	NO_FILTER,
	priceLabel,
	saveFavourites
} from './catalog.js';

function model(id: string, changes: Partial<CatalogModel> = {}): CatalogModel {
	return {
		id,
		openrouter_id: id.includes('/') ? id : `vendor/${id}`,
		name: id,
		vendor: id.includes('/') ? id.split('/')[0] : 'vendor',
		context_length: 128_000,
		input_usd_per_mtok: 0.1,
		output_usd_per_mtok: 0.4,
		reasoning: false,
		moderated: false,
		free: false,
		verified: false,
		high_price: false,
		price_source: 'openrouter list',
		...changes
	};
}

const CATALOG = [
	model('glm-flash', {
		name: 'GLM 5.3 Flash',
		openrouter_id: 'z-ai/glm-5.3-flash',
		vendor: 'z-ai',
		verified: true,
		input_usd_per_mtok: 0.04,
		output_usd_per_mtok: 0.08
	}),
	model('deepseek-flash', {
		name: 'DeepSeek Flash',
		openrouter_id: 'deepseek/v4.1-flash',
		vendor: 'deepseek',
		verified: true,
		input_usd_per_mtok: 0.05,
		output_usd_per_mtok: 0.57,
		reasoning: true
	}),
	model('anthropic/claude-big', {
		name: 'Claude Big',
		input_usd_per_mtok: 15,
		output_usd_per_mtok: 75,
		high_price: true,
		context_length: 200_000
	}),
	model('meta/llama-free:free', {
		name: 'Llama Free',
		free: true,
		input_usd_per_mtok: 0,
		output_usd_per_mtok: 0,
		context_length: 8_000
	})
];

const ids = (models: CatalogModel[]) => models.map((m) => m.id);

describe('filterCatalog', () => {
	it('keeps everything without a filter, in the catalog order', () => {
		expect(ids(filterCatalog(CATALOG, NO_FILTER))).toEqual(ids(CATALOG));
	});

	it('searches name, id and vendor, every word', () => {
		expect(ids(filterCatalog(CATALOG, { ...NO_FILTER, query: 'flash' }))).toEqual([
			'glm-flash',
			'deepseek-flash'
		]);
		expect(ids(filterCatalog(CATALOG, { ...NO_FILTER, query: 'Z-AI flash' }))).toEqual([
			'glm-flash'
		]);
		expect(ids(filterCatalog(CATALOG, { ...NO_FILTER, query: 'anthropic' }))).toEqual([
			'anthropic/claude-big'
		]);
	});

	it('filters by price, reasoning, verification, context and favourites', () => {
		expect(ids(filterCatalog(CATALOG, { ...NO_FILTER, maxOutputUsd: 1 }))).toEqual([
			'glm-flash',
			'deepseek-flash',
			'meta/llama-free:free'
		]);
		expect(ids(filterCatalog(CATALOG, { ...NO_FILTER, reasoning: true }))).toEqual([
			'deepseek-flash'
		]);
		expect(ids(filterCatalog(CATALOG, { ...NO_FILTER, verifiedOnly: true }))).toEqual([
			'glm-flash',
			'deepseek-flash'
		]);
		expect(ids(filterCatalog(CATALOG, { ...NO_FILTER, minContext: 150_000 }))).toEqual([
			'anthropic/claude-big'
		]);
		expect(
			ids(filterCatalog(CATALOG, { ...NO_FILTER, only: new Set(['anthropic/claude-big']) }))
		).toEqual(['anthropic/claude-big']);
	});
});

describe('cheapSeats', () => {
	it('fills the seats with the cheapest verified paid models, different ones first', () => {
		expect(cheapSeats(CATALOG, 3)).toEqual(['glm-flash', 'deepseek-flash', 'glm-flash']);
	});

	it('is empty when no verified paid model is known', () => {
		expect(
			cheapSeats(
				CATALOG.filter((m) => !m.verified),
				2
			)
		).toEqual([]);
	});
});

describe('priceLabel', () => {
	it('shows the price per million tokens in and out', () => {
		expect(priceLabel(CATALOG[0])).toBe('$0.040 / $0.080');
		expect(priceLabel(CATALOG[2])).toBe('$15.00 / $75.00');
		expect(priceLabel(CATALOG[3])).toBe('$0 / $0');
	});
});

describe('favourites', () => {
	it('are kept in the browser storage', () => {
		const store = new Map<string, string>();
		const storage = {
			getItem: (key: string) => store.get(key) ?? null,
			setItem: (key: string, value: string) => void store.set(key, value)
		};

		saveFavourites(storage, new Set(['glm-flash', 'anthropic/claude-big']));

		expect(loadFavourites(storage)).toEqual(new Set(['anthropic/claude-big', 'glm-flash']));
	});

	it('are empty without storage or with broken data', () => {
		expect(loadFavourites(undefined)).toEqual(new Set());
		expect(loadFavourites({ getItem: () => 'not json' })).toEqual(new Set());
		expect(loadFavourites({ getItem: () => '{"a": 1}' })).toEqual(new Set());
	});
});
