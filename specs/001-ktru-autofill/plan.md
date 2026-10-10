# Implementation Plan: Автозаполнение характеристик СТЕ по КТРУ

**Branch**: `001-ktru-autofill` | **Date**: 2026-10-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ktru-autofill/spec.md`

## Summary

Веб-сервис принимает свободное описание товара (одежда / мебель / инструменты), находит кандидатов
КТРУ гибридным поиском, извлекает и унифицирует характеристики по справочнику КТРУ, пошагово
сужает множество кодов, выявляет ошибки с обоснованием и выдаёт итоговый код либо конкретные шаги
уточнения. Горячий путь — детерминированные правила + классический поиск (BM25 + fuzzy) на CPU,
без LLM; опциональный компактный эмбеддер. Фронт — SPA в стиле Портала поставщиков.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5 / Node 22 (frontend)

**Primary Dependencies**: FastAPI, uvicorn, pydantic v2, lxml, rapidfuzz, rank-bm25, pymorphy3,
numpy, openpyxl (ETL/eval only); опционально sentence-transformers / onnxruntime
(`intfloat/multilingual-e5-small`). Frontend: Vite, React 18, TypeScript.

**Storage**: SQLite `data/build/ktru.sqlite` (нормализованный КТРУ) + read-only артефакт индекса
`data/build/index.pkl`, загружается в память при старте.

**Testing**: pytest (unit, contract, integration, eval), Playwright (e2e smoke).

**Target Platform**: Linux server (Docker), браузер.

**Project Type**: web application (backend + frontend).

**Performance Goals**: p95 `analyze` ≤ 300 мс на CPU без эмбеддера, ≤ 800 мс с эмбеддером;
≥ 50 RPS на реплику.

**Constraints**: офлайн; VRAM 0 ГБ на горячем пути (лимит 40 ГБ не используется); RAM реплики ≤ 2 ГБ.

**Scale/Scope**: ~81 тыс. актуальных позиций КТРУ, из них в скоупе 3 категорий ~15–20 тыс.;
одна позиция на запрос.

## Constitution Check

| Принцип | Как соблюдается | Статус |
|---|---|---|
| I. КТРУ — источник истины | ETL только из `*actual*`; status=ACTIVE; xlsx — синонимы и тесты | PASS |
| II. Открытые лёгкие модели | Без LLM; опц. e5-small (118M, CPU); нет внешних API | PASS |
| III. Объяснимость | Каждая сущность ответа имеет `reason` и `confidence` | PASS |
| IV. Тесты на реальных/битых данных | eval-набор из КТРУ + xlsx, генератор ошибок, метрики одной командой | PASS |
| V. Stateless, масштабируемость | API без состояния, индекс read-only, N реплик за nginx | PASS |
| VI. Простота | Правила → fuzzy → BM25 → (опц.) эмбеддер | PASS |

Post-design re-check: PASS (нарушений нет, Complexity Tracking пуст).

## Project Structure

### Documentation (this feature)

```text
specs/001-ktru-autofill/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/  (openapi.yaml, analyze-response.example.json)
└── tasks.md
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── app/                 # FastAPI: main.py, api.py, schemas.py (контракт), deps.py
├── etl/                 # parse_ktru.py, categories.py, okei.py, build_index.py, xlsx_loader.py
├── engine/              # normalize.py, units.py, retrieve.py, extract.py, narrow.py,
│                        # validate.py, recommend.py, pipeline.py, lexicon.py
└── tests/               # unit/, contract/, integration/, fixtures/
eval/                    # build_cases.py, run_eval.py, cases/*.jsonl, report.md
frontend/                # Vite + React + TS: src/{api,components,styles}
deploy/                  # Dockerfile.backend, Dockerfile.frontend, nginx.conf, docker-compose.yml
docs/                    # bpmn/process.bpmn(+png), architecture.md, presentation/, demo-script.md
data/                    # исходные данные (не в git) + build/ артефакты
Makefile                 # make etl | dev | test | eval | up
```

**Structure Decision**: веб-приложение из двух частей (backend/ + frontend/), общий контракт
`backend/app/schemas.py` ⇄ `frontend/src/api/types.ts` ⇄ `contracts/openapi.yaml`.

## Complexity Tracking

Нарушений конституции нет.
