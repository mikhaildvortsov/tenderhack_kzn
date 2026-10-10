from engine.lexicon import format_value, is_code_char, position_detail
from engine.models import CharRec, ValueRec
from tests.fixtures.mini_index import build_mini_index


def _code_char():
    return CharRec(name="Тип исполнения рукоятки", norm_name="тип исполнение рукоятка", type=2, kind=2, required=False,
                   values=[ValueRec("concrete", value=float(i)) for i in (1, 2, 3, 4)])


def test_unitless_code_display():
    c = _code_char()
    assert is_code_char(c)
    assert [format_value(v, code=True) for v in c.values][0] == "1 (код значения КТРУ)"
    assert format_value(c.values[0]) == "1"


def test_sizes_and_units_are_not_codes():
    size = CharRec(name="Российский размер", norm_name="российский размер", type=2, kind=2, required=True,
                   values=[ValueRec("concrete", value=52.0)])
    assert not is_code_char(size)
    mass = CharRec(name="Тип", norm_name="тип", type=2, kind=2, required=True,
                   values=[ValueRec("concrete", value=1.0, unit_code="166", unit_name="Килограмм")])
    assert not is_code_char(mass)


def test_position_detail_and_allowed_values_mark_codes():
    from engine.pipeline import _allowed
    idx = build_mini_index()
    idx.positions["25.73.30.141-00000001"].chars.append(_code_char())
    d = position_detail(idx, "25.73.30.141-00000001")
    ch = next(c for c in d.characteristics if c.name == "Тип исполнения рукоятки")
    assert ch.values[0].display == "1 (код значения КТРУ)"
    vals, _, _ = _allowed(idx, "25.73.30.141-00000001", "тип исполнение рукоятка")
    assert vals == ["1 (код значения КТРУ)", "2 (код значения КТРУ)", "3 (код значения КТРУ)", "4 (код значения КТРУ)"]
    mass, _, _ = _allowed(idx, "25.73.30.141-00000001", "масса молоток")
    assert mass and not any("код значения" in v for v in mass)
