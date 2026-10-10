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
