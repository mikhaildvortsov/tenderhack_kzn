import json
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from app.schemas import AnalyzeRequest, AnalyzeResponse, Example, Health, KtruPosition

router = APIRouter()

EXAMPLES = [
    Example(category="tools", text="Пила торцовочная, тип питания: От аккумуляторных батарей, мощность 679 Вт", note="Чистый кейс: позиция определена однозначно (КТРУ 28.24.11.000-00000027)"),
    Example(category="tools", text="молатак слесарный 500г", note="Опечатка: «молатак» -> «молоток», единицы приведены к кг"),
    Example(category="tools", text="vjkjnjr 800 г", note="Неверная раскладка клавиатуры: «vjkjnjr» -> «молоток»"),
    Example(category="tools", text="молоток длина рукоятки 5 кг", note="Ошибка единиц: длина указана в килограммах, ожидаются мм"),
    Example(category="tools", text="Ножницы канцелярские, длина, max 96 мм", note="Значение вне допустимого диапазона КТРУ"),
    Example(category="tools", text="молоток слесарный 500 г, длина рукоятки 300 мм", note="Неоднозначно (2 позиции): уточните «материал бойка сталь» и получите код"),
    Example(category="clothing", text="Шорты детские, рост 2000 мм, половой признак: Для девочки", note="Чистый кейс: единицы исправлены автоматически, 2000 мм -> 200 см"),
    Example(category="clothing", text="шорты дтеские для девочки", note="Опечатка в названии: «дтеские» -> «детские»"),
    Example(category="clothing", text="Шорты детские, рост 250 см", note="Рост вне допустимого диапазона КТРУ"),
    Example(category="clothing", text="куртка мужская зимняя размер 52", note="Неоднозначность: система предложит, что уточнить в первую очередь"),
    Example(category="furniture", text="Матрац, тип матраца: Смешанный, вид матраца: С независимыми пружинными блоками", note="Позиция найдена; не хватает обязательных длины, ширины, высоты"),
    Example(category="furniture", text="Стол игровой для дошкольных учреждений, ширина столешницы 975 кг", note="Ошибка единиц: ширина в килограммах, исправление на «мм»"),
    Example(category="furniture", text="Матрац, ширина 2168 см", note="Значение вне допустимого диапазона КТРУ"),
    Example(category="furniture", text="стол", note="Неоднозначность: 66 кандидатов, система предложит вопросы по информационному выигрышу"),
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
