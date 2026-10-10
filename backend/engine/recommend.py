"""Recommendations: max information gain clarifications (ambiguous), fixes (not_found), additions (resolved)."""
from __future__ import annotations

import math
from collections import Counter

from app.schemas import Recommendation
from engine import units as U
from engine.extract import CharInfo, Ext, char_unit
from engine.models import KtruIndex

MAX_RECS = 3
MAX_OPTIONS = 8


def _entropy(counts) -> float:
    n = sum(counts)
    return -sum(c / n * math.log2(c / n) for c in counts if c) if n else 0.0


def _expected(counts) -> int:
    n = sum(counts)
    return max(1, round(sum(c * c for c in counts) / n)) if n else 0


def clarify(index: KtruIndex, alive: list[str], exts: list[Ext]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    if len(alive) < 2:
        return recs
    names = Counter(index.positions[c].name for c in alive)
    if len(names) > 1:
        recs.append(Recommendation(
            id="clarify:name", kind="clarify", characteristic=None,
            message=f"Уточните вид товара: подходят {len(names)} наименований КТРУ",
            options=[n for n, _ in names.most_common(MAX_OPTIONS)], expected_remaining=_expected(names.values())))
    done = {e.key for e in exts}
    sigs: dict[str, dict[str, tuple]] = {}
    meta: dict[str, tuple[str, bool]] = {}
    for code in alive:
        for c in index.positions[code].chars:
            if c.norm_name in done:
                continue
            u = char_unit(index, c)
            if c.type == 2 and u is None:
                continue  # unitless numeric codes (noise in KTRU) are not useful questions
            sigs.setdefault(c.norm_name, {})[code] = tuple(sorted(U.fmt_value(v, u) for v in c.values))
            if c.norm_name not in meta:
                meta[c.norm_name] = (c.name, c.required)
    scored = []
    N = len(alive)
    for key, by_code in sigs.items():
        groups = Counter(by_code.get(code, ("—",)) for code in alive)
        if len(groups) < 2:
            continue
        h = _entropy(groups.values())
        opt_cnt: Counter = Counter()
        for code, sig in by_code.items():
            opt_cnt.update(set(sig))
        options = [o for o, _ in opt_cnt.most_common(MAX_OPTIONS) if o]
        if not options:
            continue
        exp = round(sum(opt_cnt[o] for o in options) / len(options)) if options else N
        name, req = meta[key]
        scored.append((h + (0.1 if req else 0.0), key, name, options, max(1, min(exp, N))))
    scored.sort(key=lambda x: -x[0])
    for _, key, name, options, exp in scored[: MAX_RECS - len(recs)]:
        recs.append(Recommendation(id=f"clarify:{key}", kind="clarify", characteristic=name,
                                   message=f"Уточните «{name}» — это сильнее всего сузит выбор",
                                   options=options, expected_remaining=exp))
    if not recs:
        codes = alive[:MAX_OPTIONS]
        recs.append(Recommendation(
            id="clarify:code", kind="clarify", characteristic=None,
            message=f"Позиции КТРУ ({len(alive)}) не различаются по указанным признакам — выберите позицию "
                    f"вручную или добавьте характеристики",
            options=codes, expected_remaining=1))
    return recs[:MAX_RECS]


def fixes(index: KtruIndex, exts: list[Ext], has_candidates: bool, cat: dict[str, CharInfo]) -> list[Recommendation]:
    recs = []
    for e in exts:
        if not (e.conflict or e.error):
            continue
        ci = cat.get(e.key)
        opts = []
        if ci:
            c = next(iter(ci.per_pos.values()))
            opts = [U.fmt_value(v, char_unit(index, c)) for v in c.values][:MAX_OPTIONS]
        recs.append(Recommendation(id=f"fix:{e.key}", kind="fix", characteristic=e.name,
                                   message=f"Исправьте значение «{e.name}»: «{e.raw_value}{(' ' + e.raw_unit) if e.raw_unit else ''}» не соответствует КТРУ",
                                   options=opts, expected_remaining=None))
    if not has_candidates:
        recs.append(Recommendation(id="fix:name", kind="fix", characteristic=None,
                                   message="Позиция КТРУ не найдена — уточните наименование товара "
                                           "(например, «молоток слесарный», «стол письменный», «куртка мужская»)",
                                   options=[], expected_remaining=None))
    return recs[:MAX_RECS]


def additions(index: KtruIndex, code: str, exts: list[Ext]) -> list[Recommendation]:
    done = {e.key for e in exts}
    recs = []
    for c in index.positions[code].chars:
        if c.required and c.norm_name not in done and len(c.values) > 1:
            u = char_unit(index, c)
            recs.append(Recommendation(id=f"add:{c.norm_name}", kind="add", characteristic=c.name,
                                       message=f"Укажите обязательную характеристику «{c.name}»",
                                       options=[U.fmt_value(v, u) for v in c.values][:MAX_OPTIONS],
                                       expected_remaining=1))
    return recs[:MAX_RECS]


def empty() -> list[Recommendation]:
    return [Recommendation(id="add:text", kind="add", characteristic=None,
                           message="Введите наименование товара и известные характеристики, "
                                   "например «молоток слесарный 500 г, длина рукоятки 300 мм»",
                           options=["молоток слесарный 500 г", "стол письменный 1200х600х750 мм",
                                    "куртка мужская зимняя размер 52"], expected_remaining=None)]
