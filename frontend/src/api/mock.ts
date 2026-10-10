import type {
  AnalyzeRequest, AnalyzeResponse, Candidate, ExtractedCharacteristic, Example, Issue, KtruPosition, NarrowingStep, Span,
} from './types';

export const MOCK_EXAMPLES: Example[] = [
  { category: 'Инструменты', text: 'Молоток слесарный 500 г, длина рукоятки 300 мм', note: 'Код определяется однозначно' },
  { category: 'Мебель', text: 'Стол письменный', note: 'Неоднозначно — система подскажет, что уточнить' },
  { category: 'Инструменты', text: 'Молатак слесарный, длина рукоятки 5 кг', note: 'Опечатка и неверная единица' },
  { category: 'Одежда', text: 'Куртка мужская зимняя размер 52', note: 'Одежда' },
];

const sp = (text: string, sub: string | RegExp): Span | null => {
  if (typeof sub === 'string') {
    const i = text.toLowerCase().indexOf(sub.toLowerCase());
    return i < 0 ? null : { start: i, end: i + sub.length, text: text.slice(i, i + sub.length) };
  }
  const m = sub.exec(text);
  return m ? { start: m.index, end: m.index + m[0].length, text: m[0] } : null;
};

const cand = (code: string, name: string, okpd: string, okpdName: string, unit: string | null, score: number, m: number, t: number): Candidate =>
  ({ code, name, okpd2_code: okpd, okpd2_name: okpdName, unit, score, matched_chars: m, total_chars: t });

const HAMMERS: Candidate[] = [
  cand('25.73.30.110-00000012', 'Молоток слесарный', '25.73.30.110', 'Молотки и кувалды', 'Штука', 0.97, 4, 4),
  cand('25.73.30.110-00000011', 'Молоток слесарный с квадратным бойком', '25.73.30.110', 'Молотки и кувалды', 'Штука', 0.74, 3, 4),
  cand('25.73.30.110-00000013', 'Молоток столярный', '25.73.30.110', 'Молотки и кувалды', 'Штука', 0.61, 3, 4),
  cand('25.73.30.110-00000020', 'Кувалда', '25.73.30.110', 'Молотки и кувалды', 'Штука', 0.42, 2, 4),
  cand('25.73.30.110-00000014', 'Молоток-гвоздодёр', '25.73.30.110', 'Молотки и кувалды', 'Штука', 0.39, 2, 4),
];
const TABLES: Candidate[] = [
  cand('31.01.11.150-00000001', 'Стол письменный однотумбовый', '31.01.11.150', 'Столы письменные', 'Штука', 0.71, 2, 3),
  cand('31.01.11.150-00000002', 'Стол письменный двухтумбовый', '31.01.11.150', 'Столы письменные', 'Штука', 0.7, 2, 3),
  cand('31.01.11.150-00000003', 'Стол письменный угловой', '31.01.11.150', 'Столы письменные', 'Штука', 0.66, 2, 3),
  cand('31.01.11.150-00000004', 'Стол письменный без тумб', '31.01.11.150', 'Столы письменные', 'Штука', 0.64, 2, 3),
  cand('31.01.12.000-00000007', 'Стол для заседаний', '31.01.12.000', 'Столы офисные', 'Штука', 0.4, 1, 3),
  cand('31.01.12.000-00000008', 'Стол компьютерный', '31.01.12.000', 'Столы офисные', 'Штука', 0.38, 1, 3),
];

const ch = (p: Partial<ExtractedCharacteristic> & Pick<ExtractedCharacteristic, 'id' | 'name'>): ExtractedCharacteristic => ({
  raw_value: null, raw_unit: null, value: null, unit: null, value_kind: 'quantitative', span: null,
  status: 'ok', confidence: 0.9, reason: '', required: false, allowed_values: [], ...p,
});

export function mockAnalyze(req: AnalyzeRequest): AnalyzeResponse {
  const text = req.text;
  const low = text.toLowerCase();
  const ignored = new Set(req.ignored_issues ?? []);
  const base = { text, normalized_text: low.replace(/\s+/g, ' ').trim(), timings_ms: { total: 38 + (text.length % 17), retrieve: 9, extract: 14, narrow: 6 } };
  const none = { final: null, candidates: [], candidates_total: 0, characteristics: [], issues: [], narrowing: [], recommendations: [] };

  if (text.trim().length < 2) {
    return { ...base, ...none, status: 'empty', category: { id: 'unknown', name: 'Не определена', confidence: 0 }, timings_ms: { total: 1 } };
  }

  const isHammer = /мол[оа]т[оа]к/.test(low) || /молоток/.test(low);
  const isTable = /стол/.test(low);

  if (isHammer) {
    const issues: Issue[] = [];
    const chars: ExtractedCharacteristic[] = [];
    const typo = sp(text, /мол[а]так/i);
    if (typo) issues.push({
      id: 'typo-1', type: 'typo', severity: 'warning', span: typo,
      message: 'Опечатка: «' + typo.text + '» — возможно, «молоток»',
      reason: 'Слово не найдено в справочнике КТРУ; ближайшее наименование «Молоток слесарный» (расстояние Левенштейна = 1).',
      suggestion: { replacement: 'молоток', label: 'Заменить на «молоток»' }, auto_applied: false,
    });
    const mass = sp(text, /\d+([.,]\d+)?\s*(г|кг)(?![а-яё])/i);
    if (mass) chars.push(ch({
      id: 'massa', name: 'Масса молотка', raw_value: mass.text.replace(/\D*$/, '').trim(), raw_unit: /кг/i.test(mass.text) ? 'кг' : 'г',
      value: /кг/i.test(mass.text) ? mass.text.replace(/[^\d.,]/g, '') : String(parseFloat(mass.text.replace(',', '.')) / 1000), unit: 'кг', span: mass,
      status: /кг/i.test(mass.text) ? 'ok' : 'corrected', confidence: 0.93, required: false, allowed_values: ['0,2–0,4 кг', '0,4–0,8 кг', '0,8–1,5 кг'],
      reason: /кг/i.test(mass.text) ? 'Единица совпадает с КТРУ.' : 'В КТРУ масса задана в килограммах: 500 г приведено к 0,5 кг. Значение попадает в интервал 0,4–0,8 кг.',
    }));
    const handleM = sp(text, /(длин[ауы]?\s+ручки|длин[ауы]?\s+рукоятки|ручка|рукоятка)\s*[:\-]?\s*\d+([.,]\d+)?\s*(мм|см|кг|г|м)(?![а-яё])/i);
    let handleOk = false;
    if (handleM) {
      const unit = /(мм|см|кг|г|м)\s*$/i.exec(handleM.text)?.[1].toLowerCase() ?? '';
      const num = parseFloat(/\d+([.,]\d+)?/.exec(handleM.text)![0].replace(',', '.'));
      if (unit === 'кг' || unit === 'г') {
        const idUm = 'unit-1';
        if (!ignored.has(idUm)) issues.push({
          id: idUm, type: 'unit_mismatch', severity: 'error', span: handleM,
          message: 'Длина рукоятки указана в «' + unit + '» — это единица массы',
          reason: 'Характеристика «Длина рукоятки» в КТРУ измеряется в миллиметрах (ОКЕИ 003). Единица массы недопустима.',
          suggestion: { replacement: 'длина рукоятки ' + num + ' мм', label: 'Исправить на «' + num + ' мм»' }, auto_applied: false,
        });
        chars.push(ch({ id: 'handle', name: 'Длина рукоятки', raw_value: String(num), raw_unit: unit, value: String(num), unit: 'мм', span: handleM, status: 'error', confidence: 0.4, required: true,
          allowed_values: ['200–300 мм', '300–400 мм', '400–500 мм'], reason: 'Единица «' + unit + '» не соответствует характеристике; ожидаются миллиметры.' }));
        const idRg = 'range-1';
        if (num > 0 && num < 10 && !ignored.has(idRg)) issues.push({
          id: idRg, type: 'out_of_range', severity: 'warning', span: handleM,
          message: 'Значение ' + num + ' вне допустимых интервалов (200–500 мм)',
          reason: 'Допустимые интервалы у позиции 25.73.30.110-00000012: 200–300, 300–400, 400–500 мм.',
          suggestion: null, auto_applied: false,
        });
      } else {
        const mm = unit === 'см' ? num * 10 : unit === 'м' ? num * 1000 : num;
        handleOk = mm >= 200 && mm <= 500;
        chars.push(ch({ id: 'handle', name: 'Длина рукоятки', raw_value: String(num), raw_unit: unit, value: String(mm), unit: 'мм', span: handleM, required: true,
          status: unit === 'мм' ? 'ok' : 'corrected', confidence: 0.95, allowed_values: ['200–300 мм', '300–400 мм', '400–500 мм'],
          reason: unit === 'мм' ? 'Единица совпадает с КТРУ; значение попадает в интервал 300–400 мм (граница 300 относится к верхнему интервалу).' : 'Приведено к мм из «' + unit + '».' }));
      }
    } else {
      chars.push(ch({ id: 'handle', name: 'Длина рукоятки', status: 'missing', confidence: 0, required: true, allowed_values: ['200–300 мм', '300–400 мм', '400–500 мм'], reason: 'Обязательная характеристика не указана — она различает 3 из 5 оставшихся позиций.' }));
      issues.push({ id: 'miss-1', type: 'missing_required', severity: 'warning', span: null, message: 'Не указана обязательная характеристика «Длина рукоятки»', reason: 'Характеристика обязательна для позиций КТРУ 25.73.30.110-*.', suggestion: null, auto_applied: false });
    }
    const material = sp(text, /(стальн\w+|деревянн\w+|фибергласс\w*)/i);
    if (material) chars.push(ch({ id: 'material', name: 'Материал рукоятки', value_kind: 'qualitative', raw_value: material.text, value: 'Дерево', span: material, status: 'corrected', confidence: 0.7, allowed_values: ['Дерево', 'Фибергласс', 'Металл'], reason: 'Прилагательное сопоставлено с допустимым значением справочника.' }));
    chars.push(ch({ id: 'kind', name: 'Тип молотка', value_kind: 'qualitative', value: 'Слесарный', status: /слесарн/i.test(low) ? 'ok' : 'suggested', span: sp(text, /слесарн\w+/i), confidence: /слесарн/i.test(low) ? 0.96 : 0.5, allowed_values: ['Слесарный', 'Столярный', 'Кровельный'], reason: /слесарн/i.test(low) ? 'Найдено в тексте.' : 'Предложено по наиболее частой позиции.' }));

    const hasErr = issues.some((i) => i.severity === 'error');
    const resolved = handleOk && !hasErr && !typo;
    const steps: NarrowingStep[] = [
      { step: 1, stage: 'category', label: 'Категория: Инструменты', characteristic: null, value: null, before: 4812, after: 612, excluded_sample: ['31.01.11.150-00000001', '14.12.11.110-00000003', '14.13.11.120-00000010'] },
      { step: 2, stage: 'name', label: 'Наименование «молоток»', characteristic: null, value: 'молоток', before: 612, after: 24, excluded_sample: ['25.73.30.120-00000002', '25.73.30.130-00000005', '25.73.60.110-00000001'] },
    ];
    if (mass) steps.push({ step: 3, stage: 'characteristic', label: 'Масса молотка 0,5 кг', characteristic: 'Масса молотка', value: '0,5 кг', before: 24, after: 9, excluded_sample: ['25.73.30.110-00000030', '25.73.30.110-00000031'] });
    if (handleM && !hasErr) steps.push({ step: steps.length + 1, stage: 'characteristic', label: 'Длина рукоятки ' + (/\d+/.exec(handleM.text)?.[0] ?? '') + ' ' + (/(мм|см|м)\s*$/i.exec(handleM.text)?.[1] ?? ''), characteristic: 'Длина рукоятки', value: '300 мм', before: mass ? 9 : 24, after: resolved ? 1 : 3, excluded_sample: ['25.73.30.110-00000014', '25.73.30.110-00000020'] });
    steps.push({ step: steps.length + 1, stage: 'ranking', label: 'Ранжирование по близости', characteristic: null, value: null, before: steps[steps.length - 1].after, after: resolved ? 1 : Math.min(5, steps[steps.length - 1].after), excluded_sample: [] });

    const recs = resolved ? [] : [{
      id: 'rec-1', kind: 'clarify' as const, characteristic: 'Длина рукоятки', message: 'Уточните длину рукоятки',
      options: ['200–300 мм', '300–400 мм', '400–500 мм'], expected_remaining: 2,
    }];
    return {
      ...base, status: resolved ? 'resolved' : 'ambiguous',
      category: { id: 'tools', name: 'Инструменты', confidence: 0.96 },
      final: resolved ? HAMMERS[0] : null,
      candidates: resolved ? HAMMERS : HAMMERS.slice(0, 5), candidates_total: resolved ? 5 : steps[steps.length - 1].after,
      characteristics: chars, issues: issues.filter((i) => !ignored.has(i.id)), narrowing: steps, recommendations: recs,
    };
  }

  if (isTable) {
    const types = ['письменн', 'компьютерн', 'заседан'];
    const narrowed = types.some((t) => low.includes(t));
    const colorM = sp(text, /(белый|серый|дуб\w*)/i);
    const width = sp(text, /\d{3,4}\s*мм/i);
    const chars: ExtractedCharacteristic[] = [
      ch({ id: 'kind', name: 'Вид стола', value_kind: 'qualitative', value: narrowed ? 'Письменный' : null, status: narrowed ? 'ok' : 'missing', span: sp(text, /письменн\w+/i), confidence: narrowed ? 0.95 : 0, required: true, allowed_values: ['Письменный', 'Компьютерный', 'Для заседаний'], reason: narrowed ? 'Найдено в тексте.' : 'Не указан вид стола.' }),
      ch({ id: 'width', name: 'Ширина столешницы', value: width ? width.text.replace(/\D/g, '') : null, unit: 'мм', raw_value: width ? width.text.replace(/\D/g, '') : null, raw_unit: width ? 'мм' : null, span: width, status: width ? 'ok' : 'missing', confidence: width ? 0.94 : 0, required: true, allowed_values: ['1000–1200 мм', '1200–1400 мм', '1400–1600 мм'], reason: width ? 'Единица совпадает с КТРУ.' : 'Не указана; различает 3 из 4 оставшихся позиций.' }),
      ch({ id: 'color', name: 'Цвет', value_kind: 'qualitative', value: colorM ? colorM.text : null, span: colorM, status: colorM ? 'ok' : 'missing', confidence: colorM ? 0.9 : 0, allowed_values: ['Белый', 'Серый', 'Дуб'], reason: colorM ? 'Сопоставлено со значением справочника.' : 'Необязательная характеристика.' }),
    ];
    const steps: NarrowingStep[] = [
      { step: 1, stage: 'category', label: 'Категория: Мебель', characteristic: null, value: null, before: 4812, after: 1034, excluded_sample: ['25.73.30.110-00000012', '14.12.11.110-00000003'] },
      { step: 2, stage: 'name', label: 'Наименование «стол»', characteristic: null, value: 'стол', before: 1034, after: narrowed ? 18 : 46, excluded_sample: ['31.01.10.000-00000002', '31.09.11.000-00000011'] },
    ];
    if (narrowed) steps.push({ step: 3, stage: 'characteristic', label: 'Вид стола: письменный', characteristic: 'Вид стола', value: 'Письменный', before: 18, after: 4, excluded_sample: ['31.01.12.000-00000007', '31.01.12.000-00000008'] });
    steps.push({ step: steps.length + 1, stage: 'ranking', label: 'Ранжирование по близости', characteristic: null, value: null, before: steps[steps.length - 1].after, after: Math.min(6, steps[steps.length - 1].after), excluded_sample: [] });
    return {
      ...base, status: 'ambiguous', category: { id: 'furniture', name: 'Мебель', confidence: 0.91 }, final: null,
      candidates: narrowed ? TABLES.slice(0, 4) : TABLES, candidates_total: steps[steps.length - 1].before,
      characteristics: chars,
      issues: ([{ id: 'miss-t', type: 'missing_required', severity: 'warning', span: null, message: 'Не указана обязательная характеристика «Ширина столешницы»', reason: 'Характеристика обязательна для позиций КТРУ 31.01.11.150-*.', suggestion: null, auto_applied: false }] as Issue[]).filter((i) => !width && !ignored.has(i.id)),
      narrowing: steps,
      recommendations: [
        ...(narrowed ? [] : [{ id: 'rec-t1', kind: 'clarify' as const, characteristic: 'Вид стола', message: 'Уточните вид стола', options: ['Письменный', 'Компьютерный', 'Для заседаний'], expected_remaining: 4 }]),
        { id: 'rec-t2', kind: 'add' as const, characteristic: 'Ширина столешницы', message: 'Добавьте ширину столешницы', options: ['1000–1200 мм', '1200–1400 мм', '1400–1600 мм'], expected_remaining: 2 },
      ].filter((r) => !(r.characteristic === 'Ширина столешницы' && width)),
    };
  }

  return {
    ...base, ...none, status: 'not_found', category: { id: 'unknown', name: 'Не определена', confidence: 0.2 },
    issues: [{ id: 'cat-1', type: 'category_mismatch', severity: 'error', span: null, message: 'Описание не относится к поддерживаемым категориям', reason: 'Поддерживаются категории «Одежда», «Мебель», «Инструменты». Укажите название товара, например «молоток слесарный».', suggestion: null, auto_applied: false }],
    narrowing: [{ step: 1, stage: 'category', label: 'Категория не определена', characteristic: null, value: null, before: 4812, after: 0, excluded_sample: [] }],
    recommendations: [{ id: 'rec-n', kind: 'fix', characteristic: null, message: 'Начните с названия товара', options: ['Молоток слесарный', 'Стол письменный', 'Куртка мужская'], expected_remaining: null }],
  };
}

export function mockKtru(code: string): KtruPosition {
  const c = [...HAMMERS, ...TABLES].find((x) => x.code === code) ?? HAMMERS[0];
  return {
    code: c.code, name: c.name, okpd2_code: c.okpd2_code, okpd2_name: c.okpd2_name, category: c.okpd2_code.startsWith('31') ? 'furniture' : 'tools', unit: c.unit, status: 'ACTIVE',
    characteristics: [
      { code: '1', name: 'Масса молотка', type: 1, kind: 1, required: false, values: [{ min: 0.2, min_op: '>=', max: 0.4, max_op: '<', unit: 'кг', display: '0,2–0,4 кг' }, { min: 0.4, min_op: '>=', max: 0.8, max_op: '<', unit: 'кг', display: '0,4–0,8 кг' }, { min: 0.8, min_op: '>=', max: 1.5, max_op: '<', unit: 'кг', display: '0,8–1,5 кг' }] },
      { code: '2', name: 'Длина рукоятки', type: 1, kind: 1, required: true, values: [{ display: '200–300 мм', unit: 'мм', min: 200, max: 300 }, { display: '300–400 мм', unit: 'мм', min: 300, max: 400 }, { display: '400–500 мм', unit: 'мм', min: 400, max: 500 }] },
      { code: '3', name: 'Материал рукоятки', type: 2, kind: null, required: false, values: [{ text: 'Дерево', display: 'Дерево' }, { text: 'Фибергласс', display: 'Фибергласс' }, { text: 'Металл', display: 'Металл' }] },
    ],
  };
}
