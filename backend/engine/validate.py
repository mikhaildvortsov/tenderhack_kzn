"""Issues of all types (research R8) with message + reason referencing KTRU positions/characteristics."""
from __future__ import annotations

from typing import Optional

from app.schemas import Issue, Span, Suggestion
from engine import units as U
from engine.extract import CharInfo, Ext, char_unit
from engine.models import KtruIndex
from engine.retrieve import CATEGORY_NAMES
from engine.text import _morph, lemmas

_HEADS: dict[int, tuple[dict[str, set[str]], set[frozenset], dict[str, list]]] = {}
_PARTS: dict[tuple[int, str], set[str]] = {}
_SEP = {"и", "или", "а", "также"}


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


def _heads(index: KtruIndex) -> tuple[dict[str, set[str]], set[frozenset], dict[str, list]]:
    """Head lemma of every KTRU position name → its categories; lemma sets of all names; head → positions."""
    h = _HEADS.get(id(index))
    if h is None:
        cats: dict[str, set[str]] = {}
        names: set[frozenset] = set()
        by_head: dict[str, list] = {}
        for p in index.positions.values():
            ws = p.norm_name.split()
            if ws:
                cats.setdefault(ws[0], set()).add(p.category)
                names.add(frozenset(ws))
                by_head.setdefault(ws[0], []).append(p)
        h = _HEADS[id(index)] = (cats, names, by_head)
    return h


def _parts(index: KtruIndex, head: str) -> set[str]:
    """Lemmas of characteristic names/values of positions named «head …» («стол» → «тумба», «полка»)."""
    key = (id(index), head)
    pp = _PARTS.get(key)
    if pp is None:
        pp = set()
        for p in _heads(index)[2].get(head, ()):
            for c in p.chars:
                pp.update(lemmas(c.name))
                pp.update(w for v in c.values if v.text for w in lemmas(v.text))
        _PARTS[key] = pp
    return pp


def mixed_products(index: KtruIndex, nr, qtok: set, text: str) -> list[Issue]:
    """Several different products in one description («куртка мужская размер 52 и стол офисный»)."""
    cats, names, _ = _heads(index)
    toks = nr.toks
    found = []  # (token index, token) of product heads that start a new noun phrase
    for i, tk in enumerate(toks):
        if tk.kind != "word" or i in qtok or tk.lemma not in cats:
            continue
        if not any(p.tag.POS == "NOUN" and p.tag.case == "nomn" for p in _morph.parse(tk.norm)):
            continue
        prev = [t for t in toks[max(0, i - 2):i] if t.kind == "word"]
        if any(_morph.parse(t.norm)[0].tag.POS == "PREP" for t in prev):
            continue  # «стол с тумбой», «шкаф для куртки» — a complement, not a second product
        p = toks[i - 1] if i else None
        boundary = p is None or p.norm in _SEP or p.kind == "num" or (i - 1) in qtok \
            or any(ch in text[p.end:tk.start] for ch in ",;+")
        found.append((tk, boundary))
    if not found:
        return []
    first = found[0][0]
    out: list[Issue] = []
    seen = {first.lemma}
    for tk, boundary in found[1:]:
        if not boundary or tk.lemma in seen or any(first.lemma in n and tk.lemma in n for n in names):
            continue
        if any(ch in text[first.end:tk.start] for ch in ":(") or tk.lemma in _parts(index, first.lemma) \
                or first.lemma in _parts(index, tk.lemma):
            continue  # composition («костюм: куртка и брюки») or a part of the first product («стол, тумба»)
        seen.add(tk.lemma)
        c1, c2 = sorted(cats[first.lemma]), sorted(cats[tk.lemma])
        kind = ("разных категорий КТРУ (" + ", ".join(CATEGORY_NAMES[c] for c in c1) + " и "
                + ", ".join(CATEGORY_NAMES[c] for c in c2) + ")") if not set(c1) & set(c2) else "разных наименований КТРУ"
        sp = Span(start=tk.start, end=tk.end, text=text[tk.start:tk.end])
        out.append(Issue(
            id=_iid("contradiction", sp, tk.orig), type="contradiction", severity="warning", span=sp,
            message=f"В описании смешаны разные товары: «{first.orig}» и «{tk.orig}»",
            reason=f"«{first.orig}» и «{tk.orig}» — товары {kind}; ни одна позиция КТРУ не содержит оба. "
                   f"Одна карточка СТЕ описывает один товар — оставьте в описании только один.",
            suggestion=None))
    return out


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
        miss = [c.name for c in pos.chars if c.required and c.norm_name not in done and len(c.values) > 1]
        if miss:
            out.append(Issue(
                id=f"missing_required:{pos.code}", type="missing_required", severity="warning", span=None,
                message=f"Не указаны обязательные характеристики ({len(miss)}): " + ", ".join(miss),
                reason=f"В позиции КТРУ {pos.code} «{pos.name}» эти характеристики обязательны для заполнения; "
                       f"значения выберите из перечня КТРУ.",
                suggestion=None))
    return out
