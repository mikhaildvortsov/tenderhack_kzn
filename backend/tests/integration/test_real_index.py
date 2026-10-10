import statistics
import time
from pathlib import Path

import pytest

from app.schemas import AnalyzeRequest
from engine.pipeline import analyze

READY = Path(__file__).resolve().parents[3] / "data" / "build" / "READY"
pytestmark = pytest.mark.skipif(not READY.exists(), reason="реальный индекс не собран (нет data/build/READY)")

CASES = [
    ("молоток слесарный 500 г, длина рукоятки 300 мм", "tools", "Молоток"),
    ("молатак слесарный 500г", "tools", "Молоток"),
    ("vjkjnjr 800 г", "tools", "Молоток"),
    ("дрель ручная электрическая", "tools", "Дрель"),
    ("куртка мужская зимняя размер 52", "clothing", "Куртка"),
    ("перчатки рабочие", "clothing", "Перчатки"),
    ("стол письменный 1200х600х750 мм ЛДСП", "furniture", "Стол"),
    ("кресло офисное", "furniture", "Кресло"),
    ("шкаф металлический для документов", "furniture", "Шкаф"),
    ("стул ученический", "furniture", "Стул"),
]


@pytest.fixture(scope="module")
def idx():
    from engine.lexicon import load_index
    return load_index()


@pytest.mark.parametrize("text,cat,name", CASES)
def test_real_query(idx, text, cat, name):
    r = analyze(AnalyzeRequest(text=text), idx)
    assert r.category.id == cat
    assert r.candidates and r.candidates[0].name.startswith(name)
    assert r.status in ("resolved", "ambiguous")
    if r.status == "ambiguous":
        assert r.recommendations


def test_real_errors(idx):
    r = analyze(AnalyzeRequest(text="молоток длина рукоятки 5 кг"), idx)
    assert any(i.type == "unit_mismatch" for i in r.issues)
    r = analyze(AnalyzeRequest(text="футболка трикотажная рост 1940 см"), idx)
    assert any(i.type == "out_of_range" for i in r.issues)
    r = analyze(AnalyzeRequest(text="автомобиль легковой"), idx)
    assert r.status == "not_found" and any(i.type == "category_mismatch" for i in r.issues)


def test_real_latency(idx):
    texts = [c[0] for c in CASES] * 2
    ms = []
    for t in texts:
        t0 = time.perf_counter()
        analyze(AnalyzeRequest(text=t), idx)
        ms.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(ms, n=20)[-1]
    print(f"p50={statistics.median(ms):.1f}ms p95={p95:.1f}ms")
    assert p95 <= 300
