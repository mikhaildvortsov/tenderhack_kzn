# Автозаполнение характеристик СТЕ по КТРУ

Хакатон Казань. По свободному тексту («молатак слесарный 500г») система определяет позицию КТРУ, извлекает и унифицирует характеристики, находит ошибки (опечатки, раскладка, единицы, недопустимые значения), показывает сужение кандидатов и подсказывает, что уточнить. Категории: одежда, мебель, инструменты.

## Архитектура
- `etl/` — разбор XML КТРУ в индекс `data/build/index.pkl` (BM25, словарь, лексиконы значений, ОКЕИ).
- `engine/` — пайплайн: нормализация, исправление опечаток/раскладки, категория, поиск, извлечение и проверка характеристик, воронка сужения, рекомендации.
- `app/` — FastAPI (`/api/v1`), индекс грузится один раз при старте, движок вызывается в threadpool, SSE для воронки.
- `frontend/` — React + Vite UI.
- `deploy/` — Docker (backend, frontend+nginx), compose.

## Быстрый старт
```bash
make setup   # venv (uv) + зависимости + npm ci
make etl     # XML -> data/build/index.pkl
make dev     # backend :8000 + frontend :5173
make test    # pytest backend/tests
make eval    # eval/run_eval.py
```
Только API: `make api`. Без индекса сервис стартует: `/health` -> `index_loaded=false`, `/analyze` -> 503.

## Docker
```bash
make etl && make up          # UI: http://localhost:8080
docker compose -f deploy/docker-compose.yml up --build -d --scale backend=2
make logs / make down
```
Индекс монтируется read-only из `data/build` (`KTRU_INDEX=/data/build/index.pkl`).

## API (`/api/v1`, контракт: `specs/001-ktru-autofill/contracts/api.md`)
- `POST /analyze` — AnalyzeRequest -> AnalyzeResponse
- `GET /stream?text=` — SSE: `stage` (NarrowingStep), затем `result` (AnalyzeResponse)
- `GET /ktru/{code}` — карточка позиции КТРУ (404)
- `GET /examples` — демонстрационные запросы
- `GET /health` (без префикса) — статус, число позиций, версия (`APP_VERSION`)
- Swagger: `/docs`

## Структура
```
backend/{app,engine,etl,tests}  frontend/  eval/  deploy/  data/  specs/  docs/  Makefile
```

## Ограничения хакатона
Только открытые модели и алгоритмы (BM25, rapidfuzz, pymorphy3), без внешних LLM API; всё работает офлайн.
