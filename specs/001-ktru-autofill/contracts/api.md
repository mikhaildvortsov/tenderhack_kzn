# API Contract v1 (источник истины для backend/app/schemas.py и frontend/src/api/types.ts)

Base: `/api/v1`. JSON, UTF-8. OpenAPI генерируется FastAPI по `/openapi.json`.

## POST /api/v1/analyze

Request:
```ts
interface AnalyzeRequest {
  text: string;                       // 0..2000
  overrides?: { name: string; value: string; unit?: string | null }[]; // правки из таблицы
  ignored_issues?: string[];          // Issue.id, отклонённые пользователем
  selected_code?: string | null;      // пользователь выбрал кандидата вручную
}
```

Response 200:
```ts
type Status = "resolved" | "ambiguous" | "not_found" | "empty";
interface Span { start: number; end: number; text: string }
interface CategoryGuess { id: "clothing" | "furniture" | "tools" | "unknown"; name: string; confidence: number }
interface Candidate {
  code: string; name: string; okpd2_code: string; okpd2_name: string;
  unit: string | null; score: number; matched_chars: number; total_chars: number;
}
interface ExtractedCharacteristic {
  id: string;                         // стабильный: ktru char norm name
  name: string;                       // название по КТРУ
  raw_value: string | null; raw_unit: string | null;   // как во вводе
  value: string | null;               // унифицированное значение (текст или число как строка)
  unit: string | null;                // единица КТРУ (наименование ОКЕИ)
  value_kind: "quantitative" | "qualitative";
  span: Span | null;
  status: "ok" | "corrected" | "error" | "missing" | "suggested";
  confidence: number;                 // 0..1
  reason: string;                     // почему так сопоставлено/унифицировано
  required: boolean;
  allowed_values: string[];           // допустимые значения у топ-позиции (≤ 30), диапазоны вида "100–150 мм"
}
interface Issue {
  id: string;
  type: "typo" | "layout" | "unit_mismatch" | "value_not_allowed" | "out_of_range"
      | "missing_required" | "contradiction" | "unknown_characteristic" | "category_mismatch";
  severity: "error" | "warning" | "info";
  span: Span | null;
  message: string;                    // кратко, для пользователя
  reason: string;                     // обоснование со ссылкой на КТРУ
  suggestion: { replacement: string; label: string } | null; // замена span.text → replacement
  auto_applied: boolean;
}
interface NarrowingStep {
  step: number;
  stage: "category" | "name" | "characteristic" | "ranking";
  label: string;                      // "Длина рукоятки 300 мм"
  characteristic: string | null; value: string | null;
  before: number; after: number;
  excluded_sample: string[];          // до 5 кодов
}
interface Recommendation {
  id: string; kind: "add" | "clarify" | "fix";
  characteristic: string | null;
  message: string;                    // "Уточните длину рукоятки"
  options: string[];                  // варианты значений
  expected_remaining: number | null;
}
interface AnalyzeResponse {
  status: Status;
  text: string; normalized_text: string;
  category: CategoryGuess;
  final: Candidate | null;
  candidates: Candidate[];            // top-20 по score
  candidates_total: number;
  characteristics: ExtractedCharacteristic[];
  issues: Issue[];
  narrowing: NarrowingStep[];
  recommendations: Recommendation[];
  timings_ms: Record<string, number>; // {"total": 42, "retrieve": 10, ...}
}
```

## GET /api/v1/stream?text=...

SSE. События `stage` (data = NarrowingStep) по мере выполнения, финальное `result`
(data = AnalyzeResponse). Используется для анимации воронки.

## GET /api/v1/ktru/{code}

```ts
interface KtruValue { text?: string; min?: number; min_op?: string; max?: number; max_op?: string; value?: number; unit?: string | null; display: string }
interface KtruCharacteristic { code: string | null; name: string; type: 1 | 2; kind: number | null; required: boolean; values: KtruValue[] }
interface KtruPosition { code: string; name: string; okpd2_code: string; okpd2_name: string; category: string; unit: string | null; status: string; characteristics: KtruCharacteristic[] }
```
404 если нет.

## GET /api/v1/examples
`{ category: string; text: string; note: string }[]` — демонстрационные запросы.

## GET /health
`{ "status": "ok", "positions": number, "index_loaded": boolean, "version": string }`
