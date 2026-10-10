# Tasks: Автозаполнение характеристик СТЕ по КТРУ

**Input**: plan.md, research.md, data-model.md, contracts/api.md, spec.md
**Conventions**: backend — рабочая директория `backend/`, пакеты `app`, `etl`, `engine`;
venv `backend/.venv` (Python 3.11, зависимости установлены). Запуск: `cd backend && .venv/bin/python -m ...`.
Общие контракты (НЕ менять без согласования с оркестратором): `backend/engine/models.py`,
`backend/app/schemas.py`, `specs/001-ktru-autofill/contracts/api.md`.

Ключевые интерфейсы:
- `engine.lexicon.load_index(path="../data/build/index.pkl") -> KtruIndex`
- `engine.pipeline.analyze(req: AnalyzeRequest, index: KtruIndex) -> AnalyzeResponse`
- `engine.pipeline.analyze_steps(req, index) -> Iterator[NarrowingStep | AnalyzeResponse]` (последний — ответ)
- `engine.lexicon.position_detail(index, code) -> KtruPosition | None`

## Phase 1: Setup (оркестратор) ✅
- [x] T001 Структура репозитория, git, .gitignore
- [x] T002 backend venv + зависимости, pyproject
- [x] T003 Контракты: engine/models.py, app/schemas.py, contracts/api.md

## Phase 2: Foundational — данные (Агент ETL, Opus)
- [x] T010 etl/categories.py — префиксы ОКПД2 по категориям, проверка по статистике
- [x] T011 etl/okei.py — таблица единиц (код, символы, размерность, множитель)
- [x] T012 etl/parse_ktru.py — iterparse XML → SQLite (data/build/ktru.sqlite)
- [x] T013 etl/xlsx_loader.py — синонимы характеристик/значений из xlsx (Лист1, Лист2)
- [x] T014 engine/text.py — нормализация/лемматизация (общая для ETL и engine)
- [x] T015 etl/build_index.py — PositionRec + BM25 + vocab → data/build/index.pkl
- [x] T016 engine/lexicon.py — load_index, position_detail; tests/unit/test_etl.py

## Phase 3: US1+US2+US3 — движок (Агент Engine, Opus)
- [x] T020 [US1] engine/normalize.py — нормализация, spans, раскладка, опечатки
- [x] T021 [US1] engine/units.py — парсинг чисел/единиц/габаритов, конвертация, проверка range/concrete
- [x] T022 [US1] engine/retrieve.py — категория + BM25/fuzzy кандидаты
- [x] T023 [US1] engine/extract.py — извлечение характеристик (колич./качеств./да-нет)
- [x] T024 [US2] engine/narrow.py — пошаговое сужение, ранжирование, статус
- [x] T025 [US2] engine/recommend.py — information gain, рекомендации
- [x] T026 [US3] engine/validate.py — issues всех типов с обоснованием
- [x] T027 engine/pipeline.py — analyze / analyze_steps, overrides, ignored_issues, selected_code
- [x] T028 tests/unit/* на фикстурном мини-индексе + tests/integration на реальном индексе

## Phase 4: US4 — API, фронт, деплой
- [x] T030 [Агент API/Deploy, Sonnet] app/main.py, app/api.py (analyze, stream SSE, ktru, examples, health), CORS
- [x] T031 [Агент API/Deploy] Makefile, deploy/Dockerfile.backend, Dockerfile.frontend, nginx.conf, docker-compose.yml
- [x] T032 [Агент API/Deploy] tests/contract/test_api.py (TestClient, схема ответа)
- [x] T040 [Агент Frontend, Sonnet] Vite+React+TS, types.ts по контракту, стиль Портала поставщиков
- [x] T041 [Агент Frontend] Ввод с подсветкой spans, таблица характеристик (редактируемая → overrides)
- [x] T042 [Агент Frontend] Воронка сужения, кандидаты, карточка КТРУ, issues (применить/игнорировать), рекомендации (клик → дописать)
- [x] T043 [Агент Frontend] Примеры, состояния empty/loading/error, адаптивность; Playwright smoke (mock-режим; реальный API проверен скриншотами агента интеграции)

## Phase 5: Качество
- [x] T050 [Агент Eval, Sonnet] eval/build_cases.py — синтетика из КТРУ + порча + реальные из xlsx
- [x] T051 [Агент Eval] eval/run_eval.py → eval/report.md (метрики SC-001..SC-005)

## Phase 6: Защита
- [x] T060 [Агент Docs, Sonnet] docs/bpmn/process.bpmn (BPMN 2.0) + PNG/SVG
- [x] T061 [Агент Docs] docs/architecture.md (схема компонентов, обоснование технологий)
- [x] T062 [Агент Docs] docs/presentation (5 и 7 мин), docs/demo-script.md, README.md

## Phase 7: Интеграция (оркестратор)
- [x] T070 Сквозной прогон: make etl → make test → make eval → UI-проверка
- [x] T071 Тюнинг по eval-отчёту (итерации с агентами Engine)
- [x] T072 /speckit-analyze, /speckit-converge

## Phase 8: Convergence

- [x] T073 Выдавать issue `contradiction`, когда в описании смешаны товары разных категорий/наименований («куртка мужская размер 52 и стол офисный» сейчас → ambiguous без issue) per spec Edge Cases / FR-008 (partial)
- [x] T074 Когда число с единицей одинаково подходит к нескольким характеристикам кандидатов, предлагать пользователю варианты (Recommendation kind=clarify с options = названия характеристик) per spec Edge Cases (missing)
- [x] T075 При отклонённом исправлении опечатки (ignored_issues) не возвращать «пустой» результат молча: сообщать, что слово не найдено в справочнике, и предлагать ввести название иначе per US3/AC5, FR-010 (partial)
- [x] T076 В карточке КТРУ и allowed_values помечать числовые коды без единиц (например «Тип исполнения рукоятки: 1, 2, 3, 4») как «код значения по КТРУ», чтобы пользователь понимал источник per FR-014 (partial)
