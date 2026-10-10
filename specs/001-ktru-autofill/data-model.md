# Data Model

## 1. Хранилище КТРУ — SQLite `data/build/ktru.sqlite`

```sql
CREATE TABLE position (
  code TEXT PRIMARY KEY,           -- '25.73.30.141-00000001'
  version INTEGER NOT NULL,
  name TEXT NOT NULL,
  okpd2_code TEXT NOT NULL,
  okpd2_name TEXT,
  category TEXT NOT NULL,          -- 'clothing' | 'furniture' | 'tools'
  status TEXT NOT NULL,            -- 'ACTIVE'
  app_date_start TEXT, app_date_end TEXT,
  okei_codes TEXT,                 -- JSON ["796"]
  okei_names TEXT,                 -- JSON ["Штука"]
  parent_code TEXT,
  standards TEXT                   -- JSON ["ГОСТ Р 58518-2019"]
);
CREATE TABLE characteristic (
  id INTEGER PRIMARY KEY,
  position_code TEXT NOT NULL REFERENCES position(code),
  code TEXT,                       -- 'daec7762-c'
  name TEXT NOT NULL,
  type INTEGER,                    -- 1 качественная, 2 количественная
  kind INTEGER,                    -- 1 неизменяемая, 2 выбор одного, 3 выбор нескольких
  required INTEGER NOT NULL,       -- 0/1
  choice_type INTEGER
);
CREATE TABLE char_value (
  id INTEGER PRIMARY KEY,
  characteristic_id INTEGER NOT NULL REFERENCES characteristic(id),
  value_code TEXT,
  vtype TEXT NOT NULL,             -- 'quality' | 'range' | 'concrete'
  text TEXT,                       -- qualityDescription
  min REAL, min_op TEXT,           -- 'greater' | 'greaterOrEqual'
  max REAL, max_op TEXT,           -- 'less' | 'lessOrEqual'
  value REAL,                      -- concreteValue
  okei_code TEXT, okei_name TEXT
);
CREATE INDEX ix_char_pos ON characteristic(position_code);
CREATE INDEX ix_val_char ON char_value(characteristic_id);
```

Только `status='ACTIVE'`, только максимальная `version` на `code`, только `actual != false`
для характеристик.

## 2. Индекс в памяти — `data/build/index.pkl` (`engine/lexicon.py` грузит)

- `positions: dict[code, PositionRec]` — PositionRec(code, name, okpd2_code, okpd2_name, category,
  unit, chars: list[CharRec]); CharRec(name, norm_name, type, kind, required, values: list[ValueRec]);
  ValueRec(vtype, text, norm_text, min, min_op, max, max_op, value, unit_code, unit_name).
- `bm25` (rank_bm25.BM25Okapi) + `doc_codes: list[code]`.
- `vocab: set[str]` — леммы/словоформы из названий позиций, характеристик, значений + xlsx.
- `char_synonyms: dict[norm_name, set[str]]` — из xlsx Лист2 и KTRU.
- `value_lexicon: dict[norm_char_name, set[norm_value]]`.
- `okei: dict[code, OkeiUnit]` — OkeiUnit(code, name, symbols, dimension, factor_to_base).

## 3. Сущности ответа (см. contracts/api.md)

| Сущность | Поля (ключевые) | Правила |
|---|---|---|
| AnalyzeRequest | text, overrides[], ignored_issues[], selected_code? | text 0..2000 симв. |
| Span | start, end, text | индексы в исходном тексте |
| CategoryGuess | id, name, confidence | id ∈ clothing/furniture/tools/unknown |
| Candidate | code, name, okpd2_code, okpd2_name, unit, score, matched_chars, total_chars | top-20 |
| ExtractedCharacteristic | id, name, raw_value, raw_unit, value, unit, value_kind, span, status, confidence, reason, required, allowed_values[] | status: ok/corrected/error/missing/suggested |
| Issue | id, type, severity, span, message, reason, suggestion{replacement, label}, auto_applied | id = стабильный fingerprint `type:span.text` |
| NarrowingStep | step, stage, label, characteristic?, value?, before, after, excluded_sample[] | before ≥ after |
| Recommendation | id, kind(add/clarify/fix), characteristic, message, options[], expected_remaining | 1–3 при ambiguous/not_found |
| AnalyzeResponse | status, normalized_text, category, final, candidates, candidates_total, characteristics, issues, narrowing, recommendations, timings_ms | status: resolved/ambiguous/not_found/empty |

### Переходы статуса анализа
`empty` (нет текста/значимых токенов) → `not_found` (нет совместимых) | `ambiguous` (>1, нет
отрыва) → `resolved` (1 кандидат или отрыв ≥ порога и полное покрытие).
