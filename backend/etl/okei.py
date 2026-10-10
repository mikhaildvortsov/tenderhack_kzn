"""OKEI units table: code, symbols, dimension, factor to dimension base.

Bases: length→мм, area→м2, volume→л, mass→кг, power→Вт, voltage→В, current→А, charge→А·ч,
energy→Дж, frequency→Гц, rotation→об/мин, pressure→Па, force→Н, torque→Н·м, temperature→°C,
time→с, angle→градус, data→Гбайт, flow→м3/ч, count→шт, pair→пара, percent→%, size→размер.
Codes starting with "X-" are not real OKEI codes (units met in STE texts but absent in KTRU).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Union

from engine.models import OkeiUnit

_U = OkeiUnit

OKEI_UNITS: list[OkeiUnit] = [
    # length (base мм)
    _U("003", "Миллиметр", ("мм", "миллиметр", "миллиметров", "миллиметра", "mm"), "length", 1.0),
    _U("004", "Сантиметр", ("см", "сантиметр", "сантиметров", "сантиметра", "cm"), "length", 10.0),
    _U("005", "Дециметр", ("дм", "дециметр", "dm"), "length", 100.0),
    _U("006", "Метр", ("м", "метр", "метров", "метра", "m", "пм", "погм"), "length", 1000.0),
    _U("008", "Километр; тысяча метров", ("км", "километр", "km"), "length", 1_000_000.0),
    _U("039", "Дюйм (25,4 мм)", ("дюйм", "дюйма", "дюймов", '"', "″", "inch", "in"), "length", 25.4),
    # area (base м2)
    _U("050", "Квадратный миллиметр", ("мм2", "квмм", "кв.мм", "квадратныймиллиметр", "mm2"), "area", 1e-6),
    _U("051", "Квадратный сантиметр", ("см2", "квсм", "квадратныйсантиметр", "cm2"), "area", 1e-4),
    _U("053", "Квадратный дециметр", ("дм2", "квдм"), "area", 1e-2),
    _U("055", "Квадратный метр", ("м2", "квм", "квадратныйметр", "квадратныхметров", "m2"), "area", 1.0),
    # volume (base л)
    _U("111", "Кубический сантиметр; миллилитр", ("мл", "миллилитр", "миллилитров", "см3", "ml"), "volume", 0.001),
    _U("112", "Литр; кубический дециметр", ("л", "литр", "литров", "литра", "дм3", "l", "lt"), "volume", 1.0),
    _U("113", "Кубический метр", ("м3", "кубм", "кубометр", "m3"), "volume", 1000.0),
    # mass (base кг)
    _U("161", "Миллиграмм", ("мг", "миллиграмм", "mg"), "mass", 1e-6),
    _U("163", "Грамм", ("г", "гр", "грамм", "граммов", "грамма", "g", "gr"), "mass", 0.001),
    _U("166", "Килограмм", ("кг", "килограмм", "килограммов", "килограмма", "kg"), "mass", 1.0),
    _U("168", "Тонна; метрическая тонна (1000 кг)", ("т", "тонна", "тонн", "t"), "mass", 1000.0),
    # power (base Вт)
    _U("212", "Ватт", ("вт", "ватт", "w"), "power", 1.0),
    _U("214", "Киловатт", ("квт", "киловатт", "kw"), "power", 1000.0),
    # voltage / current / charge
    _U("222", "Вольт", ("в", "вольт", "v"), "voltage", 1.0),
    _U("223", "Киловольт", ("кв", "киловольт", "kv"), "voltage", 1000.0),
    _U("260", "Ампер", ("а", "ампер", "a"), "current", 1.0),
    _U("X-mA", "Миллиампер", ("ма", "миллиампер", "ma"), "current", 0.001),
    _U("263", "Ампер-час (3,6 кКл)", ("ач", "ампер-час", "амперчас", "ah"), "charge", 1.0),
    _U("X-mAh", "Миллиампер-час", ("мач", "миллиампер-час", "миллиамперчас", "mah"), "charge", 0.001),
    # energy (base Дж)
    _U("271", "Джоуль", ("дж", "джоуль", "j"), "energy", 1.0),
    _U("X-Wh", "Ватт-час", ("втч", "ватт-час", "wh"), "energy", 3600.0),
    _U("245", "Киловатт-час", ("квтч", "киловатт-час", "kwh"), "energy", 3_600_000.0),
    # frequency (base Гц)
    _U("290", "Герц", ("гц", "герц", "hz"), "frequency", 1.0),
    _U("291", "Килогерц", ("кгц", "килогерц", "khz"), "frequency", 1e3),
    _U("292", "Мегагерц", ("мгц", "мегагерц", "mhz"), "frequency", 1e6),
    # rotation
    _U("331", "Оборот в минуту", ("об/мин", "обмин", "оборотвминуту", "оборотоввминуту", "rpm"), "rotation", 1.0),
    _U("X-bpm", "Удар в минуту", ("уд/мин", "удмин", "ударовминуту", "ударвминуту", "bpm"), "impact_rate", 1.0),
    # pressure (base Па)
    _U("294", "Паскаль", ("па", "паскаль", "pa"), "pressure", 1.0),
    _U("297", "Килопаскаль", ("кпа", "килопаскаль", "kpa"), "pressure", 1e3),
    _U("X-MPa", "Мегапаскаль", ("мпа", "мегапаскаль", "mpa"), "pressure", 1e6),
    _U("X-bar", "Бар", ("бар", "bar"), "pressure", 1e5),
    _U("X-atm", "Атмосфера техническая", ("атм", "ат", "атмосфера", "atm"), "pressure", 98066.5),
    # force / torque
    _U("X-N", "Ньютон", ("н", "ньютон", "n"), "force", 1.0),
    _U("X-Nm", "Ньютон-метр", ("нм", "н/м", "ньютон-метр", "ньютонметр", "nm"), "torque", 1.0),
    # temperature
    _U("280", "Градус Цельсия", ("°c", "°с", "с°", "градусцельсия", "градусовцельсия"), "temperature", 1.0),
    # time (base с)
    _U("354", "Секунда", ("с", "сек", "секунда", "секунд", "s", "sec"), "time", 1.0),
    _U("355", "Минута", ("мин", "минута", "минут", "min"), "time", 60.0),
    _U("356", "Час", ("ч", "час", "часов", "часа", "h"), "time", 3600.0),
    _U("359", "Сутки", ("сут", "сутки", "суток"), "time", 86400.0),
    # angle (base градус)
    _U("2355", "Градус (плоского угла)", ("°", "град", "градус", "градусов", "градуса"), "angle", 1.0),
    _U("2356", "Минута (плоского угла)", ("′", "угловаяминута"), "angle", 1 / 60),
    _U("2357", "Секунда (плоского угла)", ("″угл", "угловаясекунда"), "angle", 1 / 3600),
    # data
    _U("2553", "Гигабайт", ("гб", "гбайт", "гигабайт", "gb"), "data", 1.0),
    _U("X-MB", "Мегабайт", ("мб", "мбайт", "мегабайт", "mb"), "data", 1 / 1024),
    _U("X-TB", "Терабайт", ("тб", "тбайт", "терабайт", "tb"), "data", 1024.0),
    # flow
    _U("598", "Кубический метр в час", ("м3/ч", "м3ч", "кубметрвчас"), "flow", 1.0),
    _U("X-lpm", "Литр в минуту", ("л/мин", "лмин", "литрвминуту"), "flow", 0.06),
    # count / pair / percent / density / size
    _U("796", "Штука", ("шт", "штука", "штук", "штуки", "pcs", "pc"), "count", 1.0),
    _U("839", "Комплект", ("компл", "комплект", "комплектов", "кт"), "set", 1.0),
    _U("715", "Пара (2 шт.)", ("пар", "пара", "пары", "пр"), "pair", 1.0),
    _U("744", "Процент", ("%", "процент", "процентов", "проц"), "percent", 1.0),
    _U("X-gsm", "Грамм на квадратный метр", ("г/м2", "гм2", "г/кв.м", "грамм/м2", "gsm"), "surface_density", 1.0),
    _U("X-kgm3", "Килограмм на кубический метр", ("кг/м3", "кгм3"), "density", 1.0),
    _U("X-dB", "Децибел", ("дб", "децибел", "db"), "sound", 1.0),
    _U("X-size", "Размер (одежда/обувь)", ("размер", "разм", "р-р", "size"), "size", 1.0),
]

_SUP = str.maketrans({"²": "2", "³": "3", "ё": "е", "×": "x"})


def norm_symbol(s: str) -> str:
    """Normalize a unit spelling: lower, ё→е, ²→2, drop spaces/dots/·/*/-, keep '/', '%', '°', '"'."""
    t = s.strip().lower().translate(_SUP)
    t = re.sub(r"[\s.·*\-]+", "", t)
    return t


_BY_CODE: dict[str, OkeiUnit] = {u.code: u for u in OKEI_UNITS}
_BY_SYMBOL: dict[str, OkeiUnit] = {}
for _u in OKEI_UNITS:
    for _s in (*_u.symbols, _u.name):
        _BY_SYMBOL.setdefault(norm_symbol(_s), _u)


def unit_by_code(code: Optional[str]) -> Optional[OkeiUnit]:
    return _BY_CODE.get(code) if code else None


def find_unit(symbol: Optional[str]) -> Optional[OkeiUnit]:
    if not symbol:
        return None
    return _BY_SYMBOL.get(norm_symbol(symbol))


def _resolve(u: Union[OkeiUnit, str, None]) -> Optional[OkeiUnit]:
    if u is None or isinstance(u, OkeiUnit):
        return u
    return unit_by_code(u) or find_unit(u)


def convert(value: Optional[float], from_unit: Union[OkeiUnit, str, None],
            to_unit: Union[OkeiUnit, str, None]) -> Optional[float]:
    """Convert value between units of the same dimension (units: OkeiUnit, OKEI code or symbol)."""
    a, b = _resolve(from_unit), _resolve(to_unit)
    if value is None or a is None or b is None or a.dimension != b.dimension or a.dimension == "other":
        return None
    if a.code == b.code:
        return float(value)
    return float(value) * a.factor / b.factor


def ensure_units(pairs: Iterable[tuple[str, Optional[str]]]) -> dict[str, OkeiUnit]:
    """Table for the index: known units + fallback 'other' units for unknown KTRU (code, name) pairs."""
    out = dict(_BY_CODE)
    for code, name in pairs:
        if code and code not in out:
            nm = name or code
            out[code] = OkeiUnit(code, nm, (norm_symbol(nm),), "other", 1.0)
    return out
