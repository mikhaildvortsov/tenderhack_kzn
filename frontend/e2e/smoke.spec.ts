import { test, expect } from '@playwright/test';

test('mock: ввод описания даёт код КТРУ, таблицу и воронку', async ({ page }) => {
  await page.goto('/?mock=1');
  await expect(page.getByText('Здесь появится код КТРУ')).toBeVisible();
  await page.getByLabel('Опишите товар своими словами').fill('молоток слесарный 500 г, длина рукоятки 300 мм');
  await expect(page.getByTestId('ktru-code')).toHaveText('25.73.30.110-00000012');
  await expect(page.getByRole('heading', { name: 'Характеристики' })).toBeVisible();
  await expect(page.getByRole('table')).toContainText('Масса молотка');
  await expect(page.getByRole('heading', { name: 'Сужение кодов КТРУ' })).toBeVisible();
  await expect(page.locator('.funnel .f-step').first()).toBeVisible();
});

test('api: вариант clarify:value дописывает «, <характеристика> <число с единицей>»', async ({ page }) => {
  await page.route('**/health', (r) => r.fulfill({ json: { status: 'ok' } }));
  await page.route('**/api/v1/examples', (r) => r.fulfill({ json: [] }));
  await page.route('**/api/v1/analyze', async (r) => {
    const { text } = r.request().postDataJSON();
    const recs = /высота 700 мм/.test(text) ? [] : [{
      id: 'clarify:value:700 мм', kind: 'clarify', characteristic: null, expected_remaining: null,
      message: 'Уточните, к какой характеристике относится «700 мм»: подходят Длина, Ширина, Высота',
      options: ['Длина', 'Ширина', 'Высота'],
    }];
    await r.fulfill({ json: {
      status: 'ambiguous', text, normalized_text: text,
      category: { id: 'furniture', name: 'Мебель', confidence: 0.9 }, final: null, candidates: [], candidates_total: 0,
      characteristics: [], issues: [], narrowing: [], recommendations: recs, timings_ms: {},
    } });
  });
  await page.goto('/');
  const box = page.getByLabel('Опишите товар своими словами');
  await box.fill('стол письменный 700 мм');
  await page.getByRole('button', { name: '+ Высота' }).click();
  await expect(box).toHaveValue('стол письменный 700 мм, высота 700 мм');
});
