"""Category scope: OKPD2 prefixes per category (checked against KTRU stats + xlsx exports).

Stats (active, max version): KTRU has ~60k active positions, 26k of them medical (32.50).
Scope covers what the xlsx exports actually contain; longest matching prefix wins.
"""
from __future__ import annotations

from typing import Optional

CATEGORY_PREFIXES: dict[str, list[str]] = {
    "clothing": [
        "14.",            # одежда, спецодежда, трикотаж, головные уборы
        "15.12",          # сумки, рюкзаки, портфели, чемоданы
        "15.20",          # обувь (в т.ч. специальная)
        "32.99.11",       # СИЗ: респираторы, каски, щитки, огнестойкая одежда
        "22.29.10.120",   # перчатки полимерные
    ],
    "furniture": [
        "31.01",          # мебель для офисов/торговли/учебных заведений
        "31.02",          # мебель кухонная
        "31.03",          # матрасы
        "31.09",          # мебель прочая, стеллажи, вешалки
        "25.99.21",       # сейфы, шкафы металлические упрочнённые
        "25.72.14.130",   # фурнитура для мебели металлическая
    ],
    "tools": [
        "25.73",          # инструмент ручной, сменный рабочий инструмент
        "28.24",          # инструмент ручной электрический/механизированный
        "27.90.31",       # аппараты сварочные/паяльные
        "26.51.33",       # инструмент мерительный (штангенциркули, линейки, угольники)
        "26.51.43.110",   # мультиметры
        "26.51.12.110",   # дальномеры, теодолиты, тахеометры
        "26.51.12.120",   # геодезические приборы (нивелиры)
        "25.71.11",       # ножи специальные/макетные, ножницы
        "25.93.15",       # электроды сварочные
        "32.91.12",       # кисти
    ],
}

EXCLUDE_PREFIXES: list[str] = [
    "31.03.12.140",       # матрасы медицинские (противопролежневые)
    "14.12.30.170",       # изделия для протезирования
]

CATEGORY_NAMES = {"clothing": "Одежда и обувь", "furniture": "Мебель", "tools": "Инструменты"}

_PAIRS = sorted(((p, c) for c, ps in CATEGORY_PREFIXES.items() for p in ps), key=lambda x: -len(x[0]))


def category_of(okpd2_code: Optional[str]) -> Optional[str]:
    if not okpd2_code:
        return None
    if any(okpd2_code.startswith(p) for p in EXCLUDE_PREFIXES):
        return None
    for p, c in _PAIRS:
        if okpd2_code.startswith(p):
            return c
    return None
