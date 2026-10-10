# Quickstart / Validation

## Prerequisites
Python 3.11, Node 22, Docker (опционально). Данные в `data/КТРУ/xml_all/` и `data/Примеры выгрузок/`.

## Локально
```bash
make setup        # venv backend (uv) + npm ci frontend
make etl          # XML → data/build/ktru.sqlite + data/build/index.pkl
make dev          # backend :8000, frontend :5173 (proxy /api)
make test         # pytest unit+contract+integration
make eval         # eval/report.md: top-1/top-3, F1, P/R ошибок, латентность
```

## Docker
```bash
make etl && docker compose -f deploy/docker-compose.yml up --build --scale backend=2
# UI: http://localhost:8080
```

## Сценарии проверки (ожидаемые результаты)
1. `молоток слесарный 500 г, длина рукоятки 300 мм` → категория tools, характеристика «Масса
   молотка» 0.5 кг (corrected unit), кандидаты сужаются, статус resolved/ambiguous с подсказкой.
2. `молатак 500г` → issue `typo` (молатак→молоток), auto_applied.
3. `vjkjnjr` → issue `layout` (→ молоток).
4. `молоток длина рукоятки 5 кг` → issue `unit_mismatch`.
5. `стол` → ambiguous, ≥1 recommendation с options.
6. `` (пусто) → status empty, понятное сообщение.
7. `curl localhost:8000/health` → `index_loaded: true`.
