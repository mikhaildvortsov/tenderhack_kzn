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
- [ ] T010 etl/categories.py — префиксы ОКПД2 по категориям, проверка по статистике
- [ ] T011 etl/okei.py — таблица единиц (код, символы, размерность, множитель)
- [ ] T012 etl/parse_ktru.py — iterparse XML → SQLite (data/build/ktru.sqlite)
- [ ] T013 etl/xlsx_loader.py — синонимы характеристик/значений из xlsx (Лист1, Лист2)
- [ ] T014 engine/text.py — нормализация/лемматизация (общая для ETL и engine)
- [ ] T015 etl/build_index.py — PositionRec + BM25 + vocab → data/build/index.pkl
- [ ] T016 engine/lexicon.py — load_index, position_detail; tests/unit/test_etl.py

## Phase 3: US1+US2+US3 — движок (Агент Engine, Opus)
- [ ] T020 [US1] engine/normalize.py — нормализация, spans, раскладка, опечатки
- [ ] T021 [US1] engine/units.py — парсинг чисел/единиц/габаритов, конвертация, проверка range/concrete
- [ ] T022 [US1] engine/retrieve.py — категория + BM25/fuzzy кандидаты
- [ ] T023 [US1] engine/extract.py — извлечение характеристик (колич./качеств./да-нет)
- [ ] T024 [US2] engine/narrow.py — пошаговое сужение, ранжирование, статус
- [ ] T025 [US2] engine/recommend.py — information gain, рекомендации
- [ ] T026 [US3] engine/validate.py — issues всех типов с обоснованием
- [ ] T027 engine/pipeline.py — analyze / analyze_steps, overrides, ignored_issues, selected_code
- [ ] T028 tests/unit/* на фикстурном мини-индексе + tests/integration на реальном индексе

## Phase 4: US4 — API, фронт, деплой
- [ ] T030 [Агент API/Deploy, Sonnet] app/main.py, app/api.py (analyze, stream SSE, ktru, examples, health), CORS
- [ ] T031 [Агент API/Deploy] Makefile, deploy/Dockerfile.backend, Dockerfile.frontend, nginx.conf, docker-compose.yml
- [ ] T032 [Агент API/Deploy] tests/contract/test_api.py (TestClient, схема ответа)
- [ ] T040 [Агент Frontend, Sonnet] Vite+React+TS, types.ts по контракту, стиль Портала поставщиков
- [ ] T041 [Агент Frontend] Ввод с подсветкой spans, таблица характеристик (редактируемая → overrides)
- [ ] T042 [Агент Frontend] Воронка сужения, кандидаты, карточка КТРУ, issues (применить/игнорировать), рекомендации (клик → дописать)
- [ ] T043 [Агент Frontend] Примеры, состояния empty/loading/error, адаптивность; Playwright smoke

## Phase 5: Качество
- [ ] T050 [Агент Eval, Sonnet] eval/build_cases.py — синтетика из КТРУ + порча + реальные из xlsx
- [ ] T051 [Агент Eval] eval/run_eval.py → eval/report.md (метрики SC-001..SC-005)

## Phase 6: Защита
- [ ] T060 [Агент Docs, Sonnet] docs/bpmn/process.bpmn (BPMN 2.0) + PNG/SVG
- [ ] T061 [Агент Docs] docs/architecture.md (схема компонентов, обоснование технологий)
- [ ] T062 [Агент Docs] docs/presentation (5 и 7 мин), docs/demo-script.md, README.md

## Phase 7: Интеграция (оркестратор)
- [ ] T070 Сквозной прогон: make etl → make test → make eval → UI-проверка
- [ ] T071 Тюнинг по eval-отчёту (итерации с агентами Engine)
- [ ] T072 /speckit-analyze, /speckit-converge
