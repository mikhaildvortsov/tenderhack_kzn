import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from app.api import router

log = logging.getLogger("ktru.api")
logging.basicConfig(level=logging.INFO)

DEFAULT_INDEX = os.path.join(os.path.dirname(__file__), "..", "..", "data", "build", "index.pkl")


def load_index_safe(app: FastAPI) -> None:
    app.state.index = None
    app.state.index_error = None
    path = os.path.abspath(os.environ.get("KTRU_INDEX", DEFAULT_INDEX))
    if not os.path.exists(path):
        app.state.index_error = f"Индекс не найден: {path}. Выполните `make etl`."
        log.warning(app.state.index_error)
        return
    t0 = time.perf_counter()
    try:
        from engine.lexicon import load_index
        app.state.index = load_index(path)
    except Exception as e:  # noqa: BLE001
        app.state.index_error = f"Не удалось загрузить индекс: {e!r}"
        log.exception("index load failed")
        return
    log.info("index loaded from %s in %.2fs", path, time.perf_counter() - t0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_index_safe(app)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="KTRU Autofill API", version=os.environ.get("APP_VERSION", "0.1.0"), lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Process-Time"],
    )

    @app.middleware("http")
    async def timing(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Process-Time"] = f"{(time.perf_counter() - t0) * 1000:.1f}ms"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def any_exc(request: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"detail": f"Внутренняя ошибка: {exc.__class__.__name__}"}, status_code=500)

    app.include_router(router)
    return app


app = create_app()
