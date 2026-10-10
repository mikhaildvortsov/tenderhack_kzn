import pytest

from engine import units
from engine.models import ValueRec
from engine.normalize import normalize
from tests.fixtures.mini_index import build_mini_index


@pytest.fixture(scope="module")
def idx():
    return build_mini_index()


def qs(idx, text):
    return units.parse_quantities(idx, normalize(text, idx).toks, text)


def test_number_with_unit_and_comma(idx):
    (q,) = qs(idx, "масса 0,5 кг")
    assert q.point == 0.5 and q.unit.code == "166" and q.raw_unit == "кг"


def test_glued_unit(idx):
    (q,) = qs(idx, "длина 30см")
    assert q.point == 30 and q.unit.code == "004"
    assert "30см" == "длина 30см"[q.start:q.end]


def test_dims(idx):
    (q,) = qs(idx, "стол 660х420х350 мм")
    assert q.dims == [660, 420, 350] and q.unit.code == "003"


def test_range_and_limits(idx):
    (q,) = qs(idx, "от 100 до 150 мм")
    assert (q.lo, q.hi) == (100, 150)
    (q,) = qs(idx, "до 2 кг")
    assert q.lo is None and q.hi == 2
    (q,) = qs(idx, "10-20 вт")
    assert (q.lo, q.hi, q.unit.code) == (10, 20, "212")


def test_ambiguous_single_letter_unit(idx):
    (q,) = qs(idx, "дрель 18 в 2 ач")[:1]
    assert q.unit.code == "222"
    (q,) = qs(idx, "размер 52 с капюшоном")
    assert q.unit is None


def test_convert_and_ranges(idx):
    g, kg, mm = idx.okei["163"], idx.okei["166"], idx.okei["003"]
    assert units.convert(500, g, kg) == pytest.approx(0.5)
    assert units.convert(5, kg, mm) is None
    v = ValueRec("range", min=0.4, min_op="greaterOrEqual", max=0.6, max_op="less")
    assert units.in_value(0.4, v) and units.in_value(0.5, v) and not units.in_value(0.6, v)
    assert units.fmt_value(v, kg) == "0.4–0.6 кг"
    assert units.fmt_num(2.0) == "2"
