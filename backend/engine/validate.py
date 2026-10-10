"""Issues of all types (research R8) with message + reason referencing KTRU positions/characteristics."""
from __future__ import annotations

from typing import Optional

from app.schemas import Issue, Span, Suggestion
from engine import units as U
from engine.extract import CharInfo, Ext, char_unit
from engine.models import KtruIndex


def _span(text: str, s: Optional[int], e: Optional[int]) -> Optional[Span]:
    if s is None or e is None:
        return None
    return Span(start=s, end=e, text=text[s:e])


def _iid(t: str, span: Optional[Span], name: str) -> str:
    return f"{t}:{span.text if span else name}"


def _allowed_summary(index: KtruIndex, ci: CharInfo, codes: list[str]) -> tuple[str, str]:
    """('≤ 2.5 кг' / list of values, position name) over alive candidates having the char."""
    chars = [ci.per_pos[c] for c in codes if c in ci.per_pos] or list(ci.per_pos.values())
    pos_name = next((index.positions[c].name for c in codes if c in ci.per_pos), "")
    if ci.quant:
        u = char_unit(index, chars[0])
        lo, hi, lo_open, hi_open = U.bounds([v for c in chars for v in c.values])
        us = f" {U.short(u)}" if u else ""
        if lo_open and hi is not None and not hi_open:
            return f"≤ {U.fmt_num(hi)}{us}", pos_name
        if hi_open and lo is not None and not lo_open:
            return f"≥ {U.fmt_num(lo)}{us}", pos_name
        if lo is not None and hi is not None and not lo_open and not hi_open:
            return f"{U.fmt_num(lo)}–{U.fmt_num(hi)}{us}", pos_name
        return ", ".join(sorted({U.fmt_value(v, u) for c in chars for v in c.values}))[:200], pos_name
    vals = sorted({v.text for c in chars for v in c.values if v.text})
    return ", ".join(vals[:12]) + ("…" if len(vals) > 12 else ""), pos_name


def issues_for(index: KtruIndex, text: str, exts: list[Ext], cat: dict[str, CharInfo], alive: list[str],
               unbound, contradictions, final: Optional[str], status: str, has_words: bool,
               category_found: bool, weak: bool = False) -> list[Issue]:
    out: list[Issue] = []
    for e in exts:
        sp = _span(text, e.start, e.end)
        ci = cat.get(e.key)
        if e.error == "unit_mismatch":
            ku = ci.unit if ci else None
            out.append(Issue(
                id=_iid("unit_mismatch", sp, e.name), type="unit_mismatch", severity="error", span=sp,
                message=f"{e.name.capitalize()} {e.raw_value} {e.raw_unit}: единица не подходит к характеристике",
                reason=f"В КТРУ характеристика «{e.name}» измеряется в единицах «{ku.name if ku else '—'}», "
                       f"а «{e.raw_unit}» — единица другой размерности.",
                suggestion=Suggestion(replacement=f"{e.raw_value} {U.short(ku)}", label=f"Заменить единицу на «{U.short(ku)}»") if ku else None))
        elif e.error == "value_not_allowed" or (e.conflict and e.kind == "qualitative"):
            allowed, pos = _allowed_summary(index, ci, alive) if ci else ("", "")
            out.append(Issue(
                id=_iid("value_not_allowed", sp, e.name), type="value_not_allowed",
                severity="error" if e.conflict else "warning", span=sp,
                message=f"«{e.raw_value}» — недопустимое значение для «{e.name}»",
                reason=f"Для позиции «{pos}» характеристика «{e.name}» допускает только: {allowed}." if pos else
                       f"Значение отсутствует в перечне КТРУ для «{e.name}».",
                suggestion=None))
        elif e.conflict and e.kind == "quantitative":
            allowed, pos = _allowed_summary(index, ci, alive) if ci else ("", "")
            raw = f"{e.raw_value}{(' ' + e.raw_unit) if e.raw_unit else ''}"
            out.append(Issue(
                id=_iid("out_of_range", sp, e.name), type="out_of_range", severity="error", span=sp,
                message=f"{e.name} {raw} — вне допустимого диапазона КТРУ",
                reason=f"{e.name} {raw} — для «{pos}» допустимо {allowed} (ни одна позиция-кандидат КТРУ не принимает это значение).",
                suggestion=None))
    for q, name in contradictions:
        sp = _span(text, q.start, q.end)
        out.append(Issue(
            id=_iid("contradiction", sp, name), type="contradiction", severity="warning", span=sp,
            message=f"Повторное значение для «{name}»: {q.display()}",
            reason=f"Для характеристики «{name}» в запросе указано несколько разных значений; учитывается первое.",
            suggestion=Suggestion(replacement="", label="Удалить повтор")))
    for q in unbound:
        sp = _span(text, q.start, q.end)
        out.append(Issue(
            id=_iid("unknown_characteristic", sp, q.display()), type="unknown_characteristic", severity="info", span=sp,
            message=f"Не удалось сопоставить «{q.display()}» с характеристикой КТРУ",
            reason="У позиций-кандидатов нет характеристики с такой единицей измерения, либо подходящих несколько — "
                   "укажите название характеристики перед значением (например, «длина 300 мм»).",
            suggestion=None))
    if has_words and category_found and weak:
        out.append(Issue(
            id="category_mismatch:" + text.strip()[:40], type="category_mismatch", severity="warning", span=None,
            message="Точной позиции КТРУ для этого товара не найдено — возможно, товар вне категорий КТРУ-скоупа",
            reason="Ни одно наименование позиции КТРУ не содержит основного слова запроса; показаны ближайшие позиции "
                   "по частичному совпадению (низкая уверенность).",
            suggestion=None))
    if has_words and not category_found:
        out.append(Issue(
            id="category_mismatch:" + text.strip()[:40], type="category_mismatch", severity="error", span=None,
            message="Товар не относится к категориям «Одежда и обувь», «Мебель», «Инструменты»",
            reason="По наименованию не найдено ни одной позиции КТРУ в поддерживаемых категориях (поиск по наименованиям, "
                   "ОКПД2 и значениям характеристик).",
            suggestion=None))
    if status == "resolved" and final:
        done = {e.key for e in exts}
        pos = index.positions[final]
        for c in pos.chars:
            if c.required and c.norm_name not in done and len(c.values) > 1:
                out.append(Issue(
                    id=f"missing_required:{c.name}", type="missing_required", severity="warning", span=None,
                    message=f"Не указана обязательная характеристика «{c.name}»",
                    reason=f"В позиции КТРУ {pos.code} «{pos.name}» характеристика «{c.name}» обязательна для заполнения.",
                    suggestion=None))
    return out
