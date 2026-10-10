import json
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from app.schemas import AnalyzeRequest, AnalyzeResponse, Example, Health, KtruPosition

router = APIRouter()

EXAMPLES = [
    Example(category="tools", text="молоток слесарный 500 г, длина рукоятки 300 мм", note="Корректный запрос, единицы приводятся к КТРУ"),
    Example(category="tools", text="молатак слесарный 500г", note="Опечатка в названии"),
    Example(category="tools", text="vjkjnjr 800 г", note="Неверная раскладка клавиатуры"),
    Example(category="tools", text="молоток длина рукоятки 5 кг", note="Ошибка единиц: длина в килограммах"),
    Example(category="tools", text="дрель аккумуляторная 18 в 2 ач", note="Электроинструмент, числовые характеристики"),
    Example(category="clothing", text="куртка мужская зимняя размер 52", note="Одежда: пол, сезон, размер"),
    Example(category="clothing", text="перчатки рабочие хб", note="Сокращение материала"),
    Example(category="furniture", text="стол офисный 1200х600х750 мм ЛДСП", note="Габариты и материал"),
    Example(category="furniture", text="кресло офисное на колёсах", note="Разговорная формулировка"),
    Example(category="furniture", text="шкаф металлический для документов", note="Уточнение назначения"),
    Example(category="furniture", text="стол", note="Неоднозначность: система предложит уточнения"),
]


def _index(request: Request):
    idx = getattr(request.app.state, "index", None)
    if idx is None:
        err = getattr(request.app.state, "index_error", None) or "Индекс не загружен"
        raise HTTPException(status_code=503, detail=err)
    return idx


def _pipeline():
    try:
        from engine import pipeline
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"Движок анализа недоступен: {e}")
    return pipeline


@router.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest, request: Request):
    index = _index(request)
    pipeline = _pipeline()
    return await run_in_threadpool(pipeline.analyze, req, index)


@router.get("/api/v1/stream")
async def stream(request: Request, text: str = Query("", max_length=2000)):
    index = _index(request)
    pipeline = _pipeline()
    req = AnalyzeRequest(text=text)

    async def gen():
        try:
            async for item in iterate_in_threadpool(iter(pipeline.analyze_steps(req, index))):
                event = "result" if isinstance(item, AnalyzeResponse) else "stage"
                yield {"event": event, "data": item.model_dump_json()}
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"detail": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(gen())


@router.get("/api/v1/ktru/{code}", response_model=KtruPosition)
async def ktru(code: str, request: Request):
    index = _index(request)
    from engine.lexicon import position_detail
    pos = await run_in_threadpool(position_detail, index, code)
    if pos is None:
        raise HTTPException(status_code=404, detail=f"Позиция КТРУ {code} не найдена")
    return pos


@router.get("/api/v1/examples", response_model=list[Example])
async def examples():
    return EXAMPLES


@router.get("/health", response_model=Health)
async def health(request: Request):
    idx = getattr(request.app.state, "index", None)
    return Health(
        status="ok",
        positions=len(idx.positions) if idx is not None else 0,
        index_loaded=idx is not None,
        version=os.environ.get("APP_VERSION", "0.1.0"),
    )
