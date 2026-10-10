import time

import pytest

from engine.lexicon import format_value, index_path, load_index, position_detail
from engine.models import ValueRec
from etl import okei, parse_ktru
from etl.categories import category_of
from etl.xlsx_loader import parse_ste_characteristics


@pytest.mark.parametrize("symbol,code", [("кг", "166"), ("мм", "003"), ("См", "004"), ("м²", "055"), ("абракадабра", None)])
def test_okei_find_unit(symbol, code):
    u = okei.find_unit(symbol)
    assert (u.code if u else None) == code


def test_okei_unit_by_code():
    assert okei.unit_by_code("796") is not None
    assert okei.unit_by_code(None) is None


@pytest.mark.parametrize("value,src,dst,expected", [
    (1.5, "м", "мм", 1500), (250, "163", "166", 0.25), (10, "см", "мм", 100),
    (1, "кг", "мм", None), (None, "кг", "г", None),
])
def test_okei_convert(value, src, dst, expected):
    got = okei.convert(value, src, dst)
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_category_of():
    assert category_of("25.73.30.141") == "tools"
    assert category_of("31.01.11.150") == "furniture"
    assert category_of("14.12.30.131") == "clothing"
    assert category_of("32.50.13.190") is None
    assert category_of(None) is None


def test_parse_ste_characteristics():
    known = ["Вес", "Тип замка", "Длина рукоятки"]
    got = parse_ste_characteristics("Вес 2.03000 кг | Тип замка ключевой | Длина рукоятки 300 мм", known)
    assert got == [("Вес", "2.03", "кг"), ("Тип замка", "ключевой", None), ("Длина рукоятки", "300", "мм")]
    assert parse_ste_characteristics("") == []
    assert parse_ste_characteristics(None) == []
    # fallback without known names: split at first number
    assert parse_ste_characteristics("Масса 1.5 кг", known_names=()) == [("Масса", "1.5", "кг")]
    assert parse_ste_characteristics("Цвет (не задано)", known_names=()) == []


@pytest.mark.parametrize("rec,expected", [
    (ValueRec(vtype="quality", text="Кулачок"), "Кулачок"),
    (ValueRec(vtype="range", min=100, min_op="greaterOrEqual", max=150, max_op="less",
              unit_code="003", unit_name="Миллиметр"), "100–150 мм"),
    (ValueRec(vtype="range", max=100, max_op="less", unit_code="003"), "< 100 мм"),
    (ValueRec(vtype="range", min=2.5, min_op="greaterOrEqual", unit_code="166"), "≥ 2.5 кг"),
    (ValueRec(vtype="concrete", value=1.5, unit_code="166"), "1.5 кг"),
    (ValueRec(vtype="concrete", value=2.0), "2"),
])
def test_format_value(rec, expected):
    assert format_value(rec) == expected


needs_index = pytest.mark.skipif(not index_path().exists(), reason="index.pkl not built")
HAMMER = "25.73.30.141-00000001"
HAMMER_XML = parse_ktru.XML_DIR / "nsiKTRUNew_all_actual_20261003020003_072.xml"


@pytest.fixture(scope="module")
def idx():
    t = time.time()
    index = load_index()
    assert time.time() - t < 3
    return index


@needs_index
@pytest.mark.skipif(not HAMMER_XML.exists(), reason="KTRU XML not available")
def test_index_matches_xml(idx):
    rows, _ = parse_ktru.parse_file(str(HAMMER_XML))
    src = next(p for p in rows if p["code"] == HAMMER)
    p = idx.positions[HAMMER]
    assert [c.name for c in p.chars] == [c["name"] for c in src["chars"]]
    for c, sc in zip(p.chars, src["chars"]):
        assert (c.type, c.kind, c.required) == (sc["type"], sc["kind"], bool(sc["required"]))
        assert [(v.vtype, v.text, v.min, v.max, v.value, v.unit_code) for v in c.values] == [
            (v["vtype"], v.get("text"), v.get("min"), v.get("max"), v.get("value"), v.get("okei_code"))
            for v in sc["values"]]


@needs_index
def test_index_smoke(idx):
    assert set(idx.meta["positions_by_category"]) == {"clothing", "furniture", "tools"}
    assert len(idx.doc_codes) == len(idx.positions) == idx.bm25.corpus_size
    p = idx.positions["25.73.30.141-00000001"]
    assert p.name == "Молоток" and p.category == "tools" and p.okpd2_code == "25.73.30.141"
    chars = {c.name: c for c in p.chars}
    assert chars["Тип"].kind == 1 and chars["Тип"].required and chars["Тип"].values[0].text == "Кулачок"
    mass = chars["Масса молотка"]
    assert mass.type == 2 and mass.kind == 2 and not mass.required
    first = mass.values[0]
    assert first.vtype == "range" and first.max == pytest.approx(0.1) and first.max_op == "less"
    assert first.unit_code == "166"
    assert {v.text for v in chars["Материал бойка"].values} == {"Сталь", "Алюминий", "Медь"}
    assert chars["Форма бойка"].kind == 3
    assert "молоток" in idx.vocab
    scores = idx.bm25.get_scores(["молоток"])
    best = idx.doc_codes[int(scores.argmax())]
    assert idx.positions[best].norm_name.startswith("молоток")


@needs_index
def test_position_detail(idx):
    d = position_detail(idx, "25.73.30.141-00000001")
    assert d is not None and d.code == "25.73.30.141-00000001" and d.category == "tools"
    by = {c.name: c for c in d.characteristics}
    assert by["Тип"].values[0].display == "Кулачок"
    assert by["Длина рукоятки"].values[0].display == "< 100 мм"
    assert by["Масса молотка"].values[-1].display == "≥ 2.5 кг"
    assert by["Длина рукоятки"].values[1].display == "100–150 мм"
    assert position_detail(idx, "00.00.00.000-00000000") is None
