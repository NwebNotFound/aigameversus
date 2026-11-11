import { expect, test } from '@playwright/test';

// A model page. No model has played in the demo stack (matches started from the UI seat random
// bots), so these look at a configured model that has not played yet.

test('a model that has not played shows what it is and that it has not played', async ({
	page
}) => {
	await page.goto('/models/glm-flash');

	await expect(page.getByRole('heading', { level: 1, name: 'glm-flash' })).toBeVisible();
	await expect(page.getByTestId('model-info')).toContainText('z-ai/');
	await expect(page.getByTestId('not-played')).toBeVisible();
	await expect(page.getByTestId('summary')).toHaveCount(0);
});

test('an unknown model is not found', async ({ page }) => {
	const response = await page.goto('/models/no-such-model');

	expect(response?.status()).toBe(404);
});
