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
    # same-name positions first: the name choice is a separate question (clarify:name)
    top_name = index.positions[alive[0]].name
    grp = [c for c in alive if index.positions[c].name == top_name]
    pool = grp if len(grp) >= 2 else alive
    sigs: dict[str, dict[str, set]] = {}
    meta: dict[str, list] = {}
    for code in pool:
        for c in index.positions[code].chars:
            if c.norm_name in done:
                continue
            u = char_unit(index, c)
            if c.type == 2 and u is None:
                continue  # unitless numeric codes (noise in KTRU) are not useful questions
            sigs.setdefault(c.norm_name, {})[code] = {U.fmt_value(v, u) for v in c.values}
            m = meta.setdefault(c.norm_name, [c.name, c.required, True])
            m[1] = m[1] or c.required
            m[2] = m[2] and len(c.values) == 1
    scored = []
    N = len(pool)
    for key, by_code in sigs.items():
        cnt: Counter = Counter()
        for code in pool:
            vals = by_code.get(code)
            for o in ({o for s_ in by_code.values() for o in s_} if vals is None else vals):
                cnt[o] += 1
        options = [o for o in cnt if o]
        if len(options) < 2 or all(cnt[o] >= N for o in options):
            continue
        # expected number of positions left after the user picks one of the values
        exp = sum(cnt[o] for o in options) / len(options)
        name, req, fixed = meta[key]
        options.sort(key=lambda o: (cnt[o], o))
        scored.append(((round(exp, 3), not fixed, not req), key, name, options[:MAX_OPTIONS], max(1, min(round(exp), N))))
    scored.sort(key=lambda x: x[0])
    for _, key, name, options, exp in scored[: MAX_RECS - len(recs)]:
        msg = (f"Уточните «{name}» — значение однозначно определит позицию КТРУ" if exp <= 1 else
               f"Уточните «{name}» — останется ≈{exp} из {N} позиций «{top_name}»")
        recs.append(Recommendation(id=f"clarify:{key}", kind="clarify", characteristic=name,
                                   message=msg, options=options, expected_remaining=exp))
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
    miss = [c for c in index.positions[code].chars if c.required and c.norm_name not in done and len(c.values) > 1]
    if not miss:
        return []
    if len(miss) == 1:
        c = miss[0]
        u = char_unit(index, c)
        return [Recommendation(id=f"add:{c.norm_name}", kind="add", characteristic=c.name,
                               message=f"Укажите обязательную характеристику «{c.name}»",
                               options=[U.fmt_value(v, u) for v in c.values][:MAX_OPTIONS], expected_remaining=1)]
    return [Recommendation(id="add:required", kind="add", characteristic=None,
                           message=f"Укажите обязательные характеристики позиции КТРУ {code} ({len(miss)}): "
                                   + ", ".join(c.name for c in miss),
                           options=[c.name for c in miss], expected_remaining=1)]


def empty() -> list[Recommendation]:
    return [Recommendation(id="add:text", kind="add", characteristic=None,
                           message="Введите наименование товара и известные характеристики, "
                                   "например «молоток слесарный 500 г, длина рукоятки 300 мм»",
                           options=["молоток слесарный 500 г", "стол письменный 1200х600х750 мм",
                                    "куртка мужская зимняя размер 52"], expected_remaining=None)]
