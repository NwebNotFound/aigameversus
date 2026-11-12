import { describe, expect, it } from 'vitest';
import { isReadOnly, refusal } from './read-only.js';

describe('read-only', () => {
	it('is on with READ_ONLY=1 or the proxy header, else off', () => {
		expect(isReadOnly('1', new Headers())).toBe(true);
		expect(isReadOnly(undefined, new Headers({ 'X-AGV-Read-Only': '1' }))).toBe(true);
		expect(isReadOnly(undefined, new Headers())).toBe(false);
		expect(isReadOnly('0', new Headers({ 'X-AGV-Read-Only': '0' }))).toBe(false);
	});

	it('lets reads pass and refuses every write and the new-match form', () => {
		expect(refusal('GET', '/matches/abc')).toBeNull();
		expect(refusal('HEAD', '/')).toBeNull();
		expect(refusal('POST', '/matches/abc/state')?.status).toBe(405);
		expect(refusal('PUT', '/x')?.status).toBe(405);
		expect(refusal('GET', '/matches/new')?.status).toBe(404);
		expect(refusal('GET', '/matches/new/werewolf')?.status).toBe(404);
		expect(refusal('GET', '/matches/newest')).toBeNull();
	});
});
