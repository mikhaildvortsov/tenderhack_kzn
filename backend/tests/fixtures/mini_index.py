"""Small hand-made KTRU index for engine unit tests (no ETL needed)."""
from __future__ import annotations

from rank_bm25 import BM25Okapi

from engine.models import CharRec, KtruIndex, OkeiUnit, PositionRec, ValueRec
from engine.text import lemmas, norm, tokens

OKEI = [
    OkeiUnit("166", "Килограмм", ("кг", "килограмм", "kg"), "mass", 1.0),
    OkeiUnit("163", "Грамм", ("г", "гр", "грамм", "g"), "mass", 0.001),
    OkeiUnit("003", "Миллиметр", ("мм", "миллиметр", "mm"), "length", 1.0),
    OkeiUnit("004", "Сантиметр", ("см", "сантиметр", "cm"), "length", 10.0),
    OkeiUnit("006", "Метр", ("м", "метр", "m"), "length", 1000.0),
    OkeiUnit("222", "Вольт", ("в", "вольт", "v"), "voltage", 1.0),
    OkeiUnit("212", "Ватт", ("вт", "ватт", "w"), "power", 1.0),
    OkeiUnit("796", "Штука", ("шт", "штука"), "count", 1.0),
    OkeiUnit("263", "Ампер-час (3,6 кКл)", ("ач", "ампер-час", "ah"), "charge", 1.0),
]


def q(*texts):
    return [ValueRec("quality", text=t, norm_text=norm(t)) for t in texts]


def rng(lo, hi, unit="166", uname="Килограмм"):
    return ValueRec("range", min=lo, min_op="greaterOrEqual" if lo is not None else None,
                    max=hi, max_op="less" if hi is not None else None, unit_code=unit, unit_name=uname)


def conc(v, unit, uname):
    return ValueRec("concrete", value=v, unit_code=unit, unit_name=uname)


def ch(name, type_, kind, required, values):
    return CharRec(name=name, norm_name=norm(name), type=type_, kind=kind, required=required, values=values)


def _hammer(i, typ, mass_ranges, handle_ranges):
    return PositionRec(
        code=f"25.73.30.141-0000000{i}", name="Молоток", okpd2_code="25.73.30.141",
        okpd2_name="Молотки", category="tools", unit="Штука",
        chars=[
            ch("Тип", 1, 1, True, q(typ)),
            ch("Масса молотка", 2, 2, True, [rng(a, b) for a, b in mass_ranges]),
            ch("Длина рукоятки", 2, 2, False, [rng(a, b, "003", "Миллиметр") for a, b in handle_ranges]),
            ch("Материал бойка", 1, 2, False, q("Сталь", "Медь")),
            ch("Наличие фиберглассовой рукоятки", 1, 2, False, q("Да", "Нет")),
        ])


def _table(code, name, mat):
    return PositionRec(
        code=code, name=name, okpd2_code="31.01.10", okpd2_name="Мебель для офисов", category="furniture",
        unit="Штука",
        chars=[
            ch("Длина", 2, 2, True, [rng(600, 2000, "003", "Миллиметр")]),
            ch("Ширина", 2, 2, True, [rng(400, 1000, "003", "Миллиметр")]),
            ch("Высота", 2, 2, True, [rng(500, 800, "003", "Миллиметр")]),
            ch("Материал столешницы", 1, 1, True, q(mat)),
        ])


def positions() -> list[PositionRec]:
    ps = [
        _hammer(1, "Слесарный", [(0.1, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)],
                [(200, 300), (300, 400)]),
        _hammer(2, "Столярный", [(0.2, 0.4), (0.4, 0.6), (0.6, 0.8)], [(250, 300), (300, 350)]),
        _hammer(3, "Кровельный", [(0.4, 0.6), (0.6, 0.8), (0.8, 1.0)], [(300, 400)]),
        _hammer(4, "Кузнечный", [(1.0, 2.0), (2.0, 2.5)], [(400, 600)]),
        _table("31.01.10.000-00000004", "Стол письменный", "ЛДСП"),
        _table("31.01.10.000-00000005", "Стол письменный", "Массив дерева"),
        _table("31.01.10.000-00000010", "Стол офисный", "ЛДСП"),
        _table("31.01.10.000-00000011", "Стол офисный", "Стекло"),
        PositionRec("31.01.11.150-00000001", "Шкаф металлический", "31.01.11.150", "Шкафы металлические",
                    "furniture", "Штука", [
                        ch("Высота", 2, 2, True, [rng(1500, 2200, "003", "Миллиметр")]),
                        ch("Количество полок", 2, 2, False, [conc(3, "796", "Штука"), conc(4, "796", "Штука")]),
                        ch("Назначение", 1, 1, True, q("Для документов")),
                    ]),
        PositionRec("31.01.12.160-00000001", "Кресло офисное", "31.01.12.160", "Мебель для сидения",
                    "furniture", "Штука", [
                        ch("Наличие подлокотников", 1, 2, True, q("Да", "Нет")),
                        ch("Наличие колес", 1, 2, False, q("Да", "Нет")),
                        ch("Материал обивки", 1, 2, False, q("Ткань", "Экокожа", "Кожа")),
                    ]),
        PositionRec("14.13.21.110-00000001", "Куртка мужская", "14.13.21.110", "Куртки мужские",
                    "clothing", "Штука", [
                        ch("Российский размер", 1, 2, True, q("48", "50", "52", "54", "56")),
                        ch("Сезон", 1, 1, True, q("Зимний")),
                        ch("Материал верха", 1, 2, False, q("Полиэстер", "Нейлон")),
                    ]),
        PositionRec("14.13.21.110-00000002", "Куртка мужская", "14.13.21.110", "Куртки мужские",
                    "clothing", "Штука", [
                        ch("Российский размер", 1, 2, True, q("48", "50", "52", "54", "56")),
                        ch("Сезон", 1, 1, True, q("Демисезонный")),
                        ch("Материал верха", 1, 2, False, q("Полиэстер", "Хлопок")),
                    ]),
        PositionRec("14.12.30.190-00000001", "Перчатки", "14.12.30.190", "Перчатки рабочие",
                    "clothing", "Пара (2 шт.)", [
                        ch("Материал", 1, 2, True, q("Хлопок", "Трикотаж")),
                    ]),
        PositionRec("28.24.11.000-00000004", "Дрель аккумуляторная", "28.24.11.000", "Дрели",
                    "tools", "Штука", [
                        ch("Напряжение аккумулятора", 2, 2, True,
                           [conc(12, "222", "Вольт"), conc(18, "222", "Вольт")]),
                        ch("Емкость аккумулятора", 2, 2, False, [rng(1.5, 2.1, "263", "Ампер-час (3,6 кКл)")]),
                    ]),
        PositionRec("28.24.11.000-00000005", "Дрель аккумуляторная", "28.24.11.000", "Дрели",
                    "tools", "Штука", [
                        ch("Напряжение аккумулятора", 2, 2, True, [conc(36, "222", "Вольт")]),
                        ch("Емкость аккумулятора", 2, 2, False, [rng(2.1, 6.0, "263", "Ампер-час (3,6 кКл)")]),
                    ]),
    ]
    for p in ps:
        p.norm_name = norm(p.name)
    return ps


def build_mini_index() -> KtruIndex:
    ps = positions()
    docs, vocab = [], set()
    syn, lex = {}, {}
    for p in ps:
        quality = [v.text for c in p.chars for v in c.values if v.vtype == "quality" and v.text]
        docs.append(lemmas(" ".join([p.name] * 3 + [p.okpd2_name] + quality)))
        for t in [p.name, p.okpd2_name, *quality, *(c.name for c in p.chars)]:
            vocab.update(tokens(t))
            vocab.update(lemmas(t, drop_stop=False))
        for c in p.chars:
            syn.setdefault(c.norm_name, set())
            lex.setdefault(c.norm_name, set()).update(v.norm_text for v in c.values if v.norm_text)
    syn[norm("Масса молотка")].add(norm("вес"))
    lex[norm("Материал бойка")].add(norm("титан"))
    return KtruIndex(
        positions={p.code: p for p in ps}, doc_codes=[p.code for p in ps], bm25=BM25Okapi(docs),
        vocab=vocab, char_synonyms=syn, value_lexicon=lex, okei={u.code: u for u in OKEI},
        meta={"fixture": True})
