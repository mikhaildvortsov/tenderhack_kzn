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


# ---- Engine-2 regressions (real descriptions) ----

def _ch(r, name):
    return next((c for c in r.characteristics if c.name == name), None)


def _errs(r, t=None):
    return [i for i in r.issues if i.severity == "error" and (t is None or i.type == t)]


@pytest.mark.parametrize("text", [
    "ЖИЛЕТ СПЕЦ, мужской, утепленный, синий с оранжевым, размер 96-100, рост 170-176",
    "Халат мужской Промкомплектация Технолог, серый с темно-серым, размер 104-108, рост 182-188см",
    'Жилет сигнальный повышенной видимости "Эконом" модель С-2.002, флуоресцентный желтый размер 120-124/182-188см',
])
def test_clothing_size_as_chest_girth_no_false_out_of_range(idx, text):
    r = analyze(AnalyzeRequest(text=text), idx)
    assert not _errs(r, "out_of_range"), [i.message for i in r.issues]


def test_clothing_size_interval_shown_converted(idx):
    r = analyze(AnalyzeRequest(text="ЖИЛЕТ СПЕЦ, мужской, утепленный, размер 96-100, рост 170-176"), idx)
    c = _ch(r, "Российский размер")
    assert c is not None and c.status != "error" and c.value == "48–50"


def test_number_unit_not_taken_across_comma(idx):
    r = analyze(AnalyzeRequest(text="Обувь валяная грубошерстная, сорт обуви 1, размер (штихмассовый) 30"), idx)
    assert not _errs(r)
    assert _ch(r, "Сорт обуви").value == "1"


def test_specific_char_name_adjacent_to_number_wins(idx):
    r = analyze(AnalyzeRequest(text="Звездочка к винторезным самооткрывающимся головкам, наружный диаметр звездочки 11 мм, "
                                    "наружный диаметр головки 155 мм"), idx)
    assert _ch(r, "Наружный диаметр звездочки").value == "11"
    assert _ch(r, "Наружный диаметр головки").value == "155"
    r = analyze(AnalyzeRequest(text="ножницы закройные/портновские, длина лезвий ножниц 74.7 мм"), idx)
    assert _ch(r, "Длина лезвий ножниц").value == "74.7"
    assert _ch(r, "Длина ножниц") is None or _ch(r, "Длина ножниц").status == "missing"


def test_yes_no_explicit_value_and_compact_span(idx):
    r = analyze(AnalyzeRequest(text="Шкаф для посуды деревянный, количество выдвижных ящиков 12 шт, наличие остекления: Нет"), idx)
    assert _ch(r, "Наличие остекления").value == "Нет"
    assert _ch(r, "Наличие выдвижных ящиков") is None or _ch(r, "Наличие выдвижных ящиков").status in ("missing", "suggested")
    r = analyze(AnalyzeRequest(text="Куртка зимняя детская с верхом из меха, рост 188 см, натуральный мех: Нет"), idx)
    c = _ch(r, "Натуральный мех")
    assert c.value == "Нет" and c.span.text.lower() == "натуральный мех: нет"
    assert _ch(r, "Тип ткани") is None or _ch(r, "Тип ткани").status in ("missing", "suggested")


def test_name_words_are_not_values(idx):
    r = analyze(AnalyzeRequest(text="Шкаф хозяйственный металлический, тип напольной опоры: Цоколь"), idx)
    c = _ch(r, "Тип каркаса")
    assert c is None or c.status in ("missing", "suggested")


def test_missing_required_is_one_aggregated_issue_and_recommendation(idx):
    r = analyze(AnalyzeRequest(text="Матрац, тип матраца: Смешанный, вид матраца: С независимыми пружинными блоками"), idx)
    assert r.status == "resolved"
    miss = [i for i in r.issues if i.type == "missing_required"]
    assert len(miss) == 1
    for n in ("Длина", "Ширина", "Высота"):
        assert n in miss[0].message
    add = [x for x in r.recommendations if x.kind == "add"]
    assert len(add) == 1 and {"Длина", "Ширина", "Высота"} <= set(add[0].options)


@pytest.mark.parametrize("text", ["Набор отвёрток Wera", "Чайник электрический", "Бумага офисная А4"])
def test_out_of_ktru_goods_are_not_found_with_low_confidence(idx, text):
    r = analyze(AnalyzeRequest(text=text), idx)
    assert r.status == "not_found"
    assert r.category.confidence <= 0.5
    assert any(i.type == "category_mismatch" for i in r.issues)
    assert any("нет позиции" in x.message for x in r.recommendations)


@pytest.mark.parametrize("text,name", [
    ("Набор для шитья", "Набор для шитья"),
    ("Набор белья для осмотра", "Набор белья"),
    ("Секция стульев многоместная", "Секция"),
    ("Жилет сигнальный повышенной видимости, размер 52", "Жилет"),
    ("Стеллаж офисный металлический", "Стеллаж"),
])
def test_in_ktru_goods_stay_found(idx, text, name):
    r = analyze(AnalyzeRequest(text=text), idx)
    assert r.status in ("resolved", "ambiguous") and r.candidates[0].name.startswith(name)


@pytest.mark.parametrize("text", [
    "Обувь валяная грубошерстная, сорт обуви 1, размер (штихмассовый) 30",
    "Жилет мужской",
    "Стул ученический",
])
def test_same_name_positions_reach_code_in_two_clarifications(idx, text):
    from app.schemas import Override
    ov = []
    r = analyze(AnalyzeRequest(text=text), idx)
    for _ in range(2):
        if r.status == "resolved":
            break
        rec = next((x for x in r.recommendations if x.kind == "clarify" and x.characteristic and x.options), None)
        if rec is None:
            break
        ov.append(Override(name=rec.characteristic, value=rec.options[0].split(" ")[0] if rec.options[0][0].isdigit() else rec.options[0]))
        r = analyze(AnalyzeRequest(text=text, overrides=ov), idx)
    same = [c for c in r.candidates if c.name == r.candidates[0].name]
    assert r.status == "resolved" or len(same) <= 2, (len(same), [x.message for x in r.recommendations])
