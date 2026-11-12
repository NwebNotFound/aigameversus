/**
 * Network rewrites for the specs, safe at the end of a test.
 *
 * A `page.route` handler can still be running when its test ends: its `route.fetch()`
 * then rejects with "Test ended" or its `response.json()` with "Response has been
 * disposed", and that late, unhandled error fails a run whose tests all passed. So:
 *
 * - import `test` and `expect` from here, not from '@playwright/test', in a spec that
 *   routes: its `page` unroutes everything at teardown and ignores late handler errors;
 * - change a real answer with `rewrite()`, which aborts quietly instead of throwing.
 *
 * `npm run lint` refuses a spec that calls `page.route` but imports `test` elsewhere
 * (scripts/check-routes.mjs).
 */
import { test as base, type Page } from '@playwright/test';

export { expect } from '@playwright/test';

export const test = base.extend({
	page: async ({ page }, use) => {
		await use(page);
		await page.unrouteAll({ behavior: 'ignoreErrors' });
	}
});

/**
 * Serve the real answer for `url` with its JSON changed by `edit` (in place, or return a
 * new body). Once the test is over the request is aborted, never thrown.
 */
export async function rewrite<T = Record<string, any>>(
	page: Page,
	url: string,
	edit: (body: T) => T | void | Promise<T | void>
): Promise<void> {
	await page.route(url, async (route) => {
		try {
			const response = await route.fetch();
			const body = (await response.json()) as T;
			const changed = (await edit(body)) ?? body;
			await route.fulfill({ response, json: changed });
		} catch {
			await route.abort().catch(() => {});
		}
	});
}
