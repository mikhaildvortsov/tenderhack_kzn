"""Step-by-step narrowing (research R7): category → name → each extracted characteristic → ranking."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.schemas import NarrowingStep
from engine.extract import CharInfo, Ext, compat
from engine.models import KtruIndex
from engine.retrieve import CATEGORY_NAMES, Retrieved

RESOLVE_GAP = 0.15
W_MATCH, W_MISSING = 0.2, 0.15


@dataclass
class Narrowed:
    steps: list[NarrowingStep] = field(default_factory=list)
    alive: list[str] = field(default_factory=list)            # ranked codes
    scores: dict[str, float] = field(default_factory=dict)
    matched: dict[str, int] = field(default_factory=dict)
    status: str = "not_found"
    final: Optional[str] = None


def filters_of(exts: list[Ext]) -> list[Ext]:
    return [e for e in exts if e.error is None]


def category_step(r: Retrieved) -> NarrowingStep:
    return NarrowingStep(step=1, stage="category", label=f"Категория: {CATEGORY_NAMES[r.category]}",
                         before=r.all_count, after=r.category_count if r.category != "unknown" else r.all_count)


def name_step(r: Retrieved, index: KtruIndex, head: str) -> NarrowingStep:
    names = sorted({index.positions[c].name for c, _, _ in r.ranked[:50]})
    label = f"Наименование: «{head}»" if head else "Наименование"
    if names:
        label += f" — {len(names)} вариант(ов) наименования"
    return NarrowingStep(step=2, stage="name", label=label, before=r.category_count if r.category != "unknown" else r.all_count,
                         after=r.name_matched)


def char_steps(index: KtruIndex, alive: list[str], exts: list[Ext], cat: dict[str, CharInfo], start_step: int):
    """Generator of (step, alive_after). Marks Ext.conflict when a value would exclude every candidate."""
    step = start_step
    for e in sorted(filters_of(exts), key=lambda x: -x.confidence):
        ci = cat.get(e.key)
        if ci is None:
            continue
        keep, drop, accept = [], [], 0
        for code in alive:
            c = ci.per_pos.get(code)
            if c is None:
                keep.append(code)
            elif compat(index, c, e):
                keep.append(code)
                accept += 1
            else:
                drop.append(code)
        unit = f" {e.unit.symbols[0]}" if e.kind == "quantitative" and e.unit is not None and e.unit.symbols else ""
        val = f"{e.value_str()}{unit}"
        if drop and not accept:
            # nobody that has this characteristic accepts the value
            if e.source == "dims" or any(compat(index, c, e) for c in ci.per_pos.values()):
                note = "противоречит другим указанным характеристикам, фильтр не применён"
                e.confidence = round(e.confidence * 0.7, 2)
            else:
                e.conflict = True
                e.status = "error"
                note = "значение недопустимо ни для одной позиции, фильтр не применён"
            st = NarrowingStep(step=step, stage="characteristic", label=f"{e.name}: {val} — {note}",
                               characteristic=e.name, value=val, before=len(alive), after=len(alive))
        else:
            st = NarrowingStep(step=step, stage="characteristic", label=f"{e.name}: {val}", characteristic=e.name,
                               value=val, before=len(alive), after=len(keep), excluded_sample=drop[:5])
            alive = keep
        step += 1
        yield st, alive


def rank(index: KtruIndex, alive: list[str], fused: dict[str, float], exts: list[Ext], cat: dict[str, CharInfo],
         step_no: int, selected: Optional[str]) -> Narrowed:
    flt = [e for e in filters_of(exts) if not e.conflict and e.key in cat]
    n = len(flt)
    scores, matched = {}, {}
    for code in alive:
        m = miss = 0
        for e in flt:
            c = cat[e.key].per_pos.get(code)
            if c is None:
                miss += 1
            elif compat(index, c, e):
                m += 1
        matched[code] = m
        s = fused.get(code, 0.0) + (W_MATCH * m / n - W_MISSING * miss / n if n else 0.0)
        scores[code] = round(s, 4)
    order = sorted(alive, key=lambda c: (-scores[c], c))
    res = Narrowed(alive=order, scores=scores, matched=matched)
    if selected and selected in index.positions:
        res.status, res.final = "resolved", selected
        if selected not in scores:
            scores[selected] = 1.0
            matched[selected] = sum(1 for e in flt if (c := cat[e.key].per_pos.get(selected)) is not None and compat(index, c, e))
            res.alive = [selected] + order
    elif not order:
        res.status = "not_found"
    elif len(order) == 1:
        res.status, res.final = "resolved", order[0]
    else:
        top, second = scores[order[0]], scores[order[1]]
        if n and matched[order[0]] == n and top - second >= RESOLVE_GAP:
            res.status, res.final = "resolved", order[0]
        else:
            res.status = "ambiguous"
    label = "Ранжирование"
    if res.final:
        label += f": выбрана позиция {res.final}" + (" (выбор пользователя)" if selected == res.final else "")
    elif order:
        label += f": лидер {order[0]}, без явного отрыва"
    res.steps.append(NarrowingStep(step=step_no, stage="ranking", label=label, before=len(alive),
                                   after=1 if res.final else len(order),
                                   excluded_sample=[c for c in order if c != res.final][:5] if res.final else []))
    return res
