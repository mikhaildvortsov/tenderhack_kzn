"""Characteristic extraction (research R6): quantities → KTRU chars by name proximity or unit dimension,
dimensions AxBxC, qualitative values by lemma n-grams / fuzzy, yes/no flags, user overrides."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz

from engine import units as U
from engine.models import CharRec, KtruIndex, OkeiUnit, PositionRec
from engine.normalize import NormResult
from engine.text import norm

GENERIC = {"наличие", "тип", "вид", "для", "с", "в", "по", "и", "или", "количество"}
YES, NO = "да", "нет"
YES_W, NO_W = {"да", "есть", "имеется"}, {"нет", "отсутствует", "отсутствуют"}
DIM_ORDER = [("длина",), ("ширина", "глубина"), ("высота",)]


@dataclass
class CharInfo:
    key: str
    name: str
    quant: bool
    unit: Optional[OkeiUnit]
    per_pos: dict[str, CharRec] = field(default_factory=dict)
    key_lemmas: frozenset = frozenset()
    syn_sets: list = field(default_factory=list)
    yes_no: bool = False
    required: bool = False
    name_lemmas: frozenset = frozenset()   # all lemmas of the char name (incl. product head words)


@dataclass
class Ext:
    key: str
    name: str
    kind: str                         # quantitative | qualitative
    raw_value: Optional[str]
    raw_unit: Optional[str]
    start: Optional[int]
    end: Optional[int]
    status: str                       # ok | corrected | error
    confidence: float
    reason: str
    lo: Optional[float] = None        # quantitative, in base units of the dimension (or raw if unit None)
    hi: Optional[float] = None
    unit: Optional[OkeiUnit] = None   # KTRU unit used for display
    in_unit: Optional[OkeiUnit] = None
    text: Optional[str] = None        # qualitative display value
    norm_text: Optional[str] = None
    error: Optional[str] = None       # unit_mismatch | value_not_allowed | out_of_range
    source: str = "text"              # text | override
    conflict: bool = False            # value excluded every candidate

    def value_str(self) -> Optional[str]:
        if self.kind == "qualitative":
            return self.text
        if self.error == "unit_mismatch":
            return U.fmt_num(self.lo if self.lo is not None else self.hi)
        f = self.unit.factor if self.unit is not None else 1.0
        lo = None if self.lo is None else self.lo / f
        hi = None if self.hi is None else self.hi / f
        if lo is not None and hi is not None and abs(lo - hi) < 1e-12:
            return U.fmt_num(lo)
        if lo is not None and hi is not None:
            return f"{U.fmt_num(lo)}–{U.fmt_num(hi)}"
        return f"≥ {U.fmt_num(lo)}" if lo is not None else f"≤ {U.fmt_num(hi)}"


def char_unit(index: KtruIndex, c: CharRec) -> Optional[OkeiUnit]:
    for v in c.values:
        u = U.unit_of_value(index, v)
        if u is not None:
            return u
    return None


def catalog(index: KtruIndex, codes: list[str]) -> dict[str, CharInfo]:
    heads = {index.positions[c].norm_name.split()[0] for c in codes if index.positions[c].norm_name}
    cat: dict[str, CharInfo] = {}
    for code in codes:
        for c in index.positions[code].chars:
            ci = cat.get(c.norm_name)
            if ci is None:
                quant = c.type == 2 or any(v.vtype in ("range", "concrete") for v in c.values)
                kl = frozenset(w for w in c.norm_name.split() if w not in GENERIC and w not in heads)
                syns = [frozenset(s.split()) - GENERIC - heads for s in index.char_synonyms.get(c.norm_name, ()) if s]
                yn = not quant and {(v.text or "").strip().lower() for v in c.values} <= {YES, NO} and bool(c.values)
                ci = cat[c.norm_name] = CharInfo(c.norm_name, c.name, quant, char_unit(index, c) if quant else None,
                                                 key_lemmas=kl, syn_sets=[s for s in syns if s], yes_no=yn,
                                                 name_lemmas=frozenset(c.norm_name.split()) - GENERIC)
            ci.per_pos[code] = c
            ci.required = ci.required or c.required
    return cat


def _mentions(ci: CharInfo, words: list[tuple[int, str]]) -> tuple[float, int, int]:
    """(score, first token idx, last token idx) of the char name/synonym mention in the query."""
    best = (0.0, -1, -1)
    for ks in [ci.key_lemmas, *ci.syn_sets]:
        if not ks:
            continue
        hits = [(i, lem) for i, lem in words if lem in ks]
        if not hits:
            continue
        # compact cluster: name words must stand together («натуральный мех», not «мех … натуральный»)
        w = len(ks) + 1
        for j, (b, _) in enumerate(hits):
            cl = [(i, lem) for i, lem in hits[: j + 1] if b - i <= w]
            score = len({lem for _, lem in cl}) / len(ks)
            if score > best[0]:
                best = (score, cl[0][0], b)
    return best


def _adjacent(ci: CharInfo, toks, q, lo_bound: int) -> int:
    """How many words of the full char name stand immediately before the number («длина лезвий ножниц 74 мм»)."""
    n, i = 0, q.i0 - 1
    while i >= max(lo_bound, 0) and i >= q.i0 - 8:
        t = toks[i]
        if t.kind == "word":
            if t.lemma not in ci.name_lemmas:
                break
            n += 1
        elif t.kind in ("num", "lat"):
            break
        i -= 1
    return n


SIZE_SKIP = ("штихмасс", "обув", "голов", "перчат", "кист", "противогаз", "топорищ")


def _hits_raw(ci: CharInfo, lo: Optional[float], hi: Optional[float]) -> bool:
    for c in ci.per_pos.values():
        for v in c.values:
            if v.vtype == "quality":
                if _num_eq(v.text, lo, hi):
                    return True
            elif U.interval_hits(lo, hi, v):
                return True
    return False


def _size_alt(ci: CharInfo, q) -> Optional[tuple[float, float]]:
    """Clothing «размер 96-100» / «120-124/182-188» is the chest girth in cm; Russian size = girth / 2."""
    if "размер" not in ci.key.split() or any(w in ci.key for w in SIZE_SKIP) or q.lo is None:
        return None
    if q.unit is not None and q.unit.dimension != "length":
        return None
    hi = q.hi if q.hi is not None else q.lo
    if not (70 <= q.lo <= hi <= 170) or _hits_raw(ci, q.lo, hi):
        return None
    alt = (q.lo / 2, hi / 2)
    return alt if _hits_raw(ci, *alt) else None


def _local(ci: CharInfo, words: list[tuple[int, str]], q, lo_bound: int) -> tuple[float, int, int]:
    """Char-name mention local to quantity q: window of 6 tokens before (not crossing the previous
    quantity) or 3 tokens after. Returns (score, first idx, last idx); before-mentions win ties."""
    best = (0.0, -1, -1)
    for ks in [ci.key_lemmas, *ci.syn_sets]:
        if not ks:
            continue
        for lo, hi in ((max(lo_bound, q.i0 - 6), q.i0 - 1), (q.i1, q.i1 + 3)):
            hits = [(i, lem) for i, lem in words if lo <= i <= hi and lem in ks]
            if not hits:
                continue
            sc = len({lem for _, lem in hits}) / len(ks)
            if sc > best[0]:
                best = (sc, min(i for i, _ in hits), max(i for i, _ in hits))
    return best


def _num_eq(text: Optional[str], lo: Optional[float], hi: Optional[float]) -> bool:
    x = U.parse_number((text or "").strip())
    if x is None or lo is None:
        return False
    return lo - 1e-9 <= x <= (hi if hi is not None else lo) + 1e-9


def compat(index: KtruIndex, c: CharRec, e: Ext) -> bool:
    if e.kind == "quantitative":
        for v in c.values:
            u = U.unit_of_value(index, v)
            if e.in_unit is None or u is None:
                lo, hi = e.lo, e.hi
                if e.in_unit is not None and u is None and e.in_unit.dimension not in ("count", "set", "pair"):
                    continue
            else:
                if u.dimension != e.in_unit.dimension:
                    continue
                lo = None if e.lo is None else e.lo / u.factor
                hi = None if e.hi is None else e.hi / u.factor
            if U.interval_hits(lo, hi, v):
                return True
        return False
    t = (e.norm_text or "").strip()
    for v in c.values:
        if v.vtype == "quality" and ((v.norm_text or "") == t or (v.text or "").strip().lower() == (e.text or "").lower()):
            return True
        if e.lo is not None and v.vtype == "quality" and _num_eq(v.text, e.lo, e.hi):
            return True
    return False


def _first_pos_with(ci: CharInfo, order: list[str]) -> Optional[str]:
    for code in order:
        if code in ci.per_pos:
            return code
    return next(iter(ci.per_pos), None)


def _allowed_desc(index: KtruIndex, c: CharRec, unit: Optional[OkeiUnit], limit: int = 6) -> str:
    vals = [U.fmt_value(v, unit) for v in c.values[:limit]]
    more = "…" if len(c.values) > limit else ""
    return ", ".join(x for x in vals if x) + more


def _quant_ext(index: KtruIndex, ci: CharInfo, q: U.Quantity, order: list[str], conf: float, how: str,
               value: Optional[float] = None, raw_value: Optional[str] = None,
               rng: Optional[tuple[float, float]] = None) -> Ext:
    lo = value if value is not None else q.lo
    hi = value if value is not None else q.hi
    if rng is not None:
        lo, hi = rng
    raw_value = raw_value or q.raw_value
    ku = ci.unit
    code = _first_pos_with(ci, order)
    c = ci.per_pos[code]
    if q.unit is not None and ku is not None and q.unit.dimension != ku.dimension:
        return Ext(ci.key, ci.name, "quantitative", raw_value, q.raw_unit, q.start, q.end, "error", conf,
                   f"Для «{ci.name}» в КТРУ используется единица «{ku.name}» ({ku.dimension}), а в запросе указано "
                   f"«{q.raw_unit}» ({q.unit.dimension}) — размерности несовместимы.",
                   lo=lo, hi=hi, unit=ku, in_unit=q.unit, error="unit_mismatch")
    in_unit = q.unit or ku
    f = in_unit.factor if in_unit is not None else 1.0
    e = Ext(ci.key, ci.name, "quantitative", raw_value, q.raw_unit, q.start, q.end, "ok", conf, "",
            lo=None if lo is None else lo * f, hi=None if hi is None else hi * f, unit=ku, in_unit=in_unit)
    shown = e.value_str()
    fit = next((ci.per_pos[k] for k in order if k in ci.per_pos and compat(index, ci.per_pos[k], e)), None)
    if fit is not None:
        c = fit
    ks = U.short(ku)
    parts = [how]
    if q.unit is None:
        parts.append(f"единица не указана — принята единица КТРУ «{ku.name if ku else '—'}»")
    elif ku is not None and q.unit.code != ku.code:
        e.status = "corrected"
        parts.insert(0, f"{q.display()} → {shown} {ks}: единица КТРУ для «{ci.name}» — {ku.name}")
    ok_here = compat(index, c, e)
    hit = next((v for v in c.values if compat(index, CharRec(c.name, c.norm_name, c.type, c.kind, c.required, values=[v]), e)), None)
    if hit is not None:
        parts.append(f"попадает в {'интервал' if hit.vtype == 'range' else 'значение'} {U.fmt_value(hit, ku)}")
    elif not ok_here:
        parts.append(f"допустимые значения: {_allowed_desc(index, c, ku)}")
    e.reason = "; ".join(p for p in parts if p)
    return e


def extract(index: KtruIndex, nr: NormResult, quantities: list[U.Quantity], order: list[str],
            cat: dict[str, CharInfo]) -> tuple[list[Ext], list[U.Quantity], list]:
    """Returns (extracted chars, unbound quantities, contradictions [(quantity, char name)])."""
    words = [(i, t.lemma) for i, t in enumerate(nr.toks) if t.kind == "word"]
    exts: list[Ext] = []
    used_tok: set[int] = set()
    for q in quantities:
        used_tok.update(range(q.i0, q.i1))
    mention = {k: _mentions(ci, words) for k, ci in cat.items()}
    bound: set[str] = set()
    unbound: list[U.Quantity] = []
    contradictions: list[tuple[U.Quantity, str]] = []

    # 1) dimensions AxBxC
    for q in quantities:
        if not q.dims:
            continue
        slots = []
        for names in DIM_ORDER[: len(q.dims)] if len(q.dims) <= 3 else []:
            k = next((k for nm in names for k, ci in cat.items() if ci.quant and k == nm and k not in slots), None)
            if k is None:
                pref = [k2 for nm in names for k2, ci in cat.items() if ci.quant and k2.split()[0] == nm and k2 not in slots]
                k = pref[0] if len(pref) == 1 else None
            slots.append(k)
        if len(q.dims) == 2 and slots[1] is None:
            slots[1] = next((k for k in cat if k.split()[0] == "высота"), None)
        any_bound = False
        for val, k, raw in zip(q.dims, slots, q.raw_value.replace("х", "x").replace("×", "x").replace("*", "x").split("x")):
            if k is None or k in bound:
                continue
            e = _quant_ext(index, cat[k], q, order, 0.8, "габариты ДxШxВ", value=val, raw_value=raw.strip())
            e.source = "dims"
            exts.append(e)
            bound.add(k)
            any_bound = True
        q.used = any_bound
        if not any_bound:
            unbound.append(q)

    # 2) single quantities
    prev_end = 0
    for q in quantities:
        lo_bound, prev_end = prev_end, q.i1
        if q.dims:
            continue
        is_count = q.unit is not None and q.unit.dimension in ("count", "set", "pair")
        best, best_key, dup_key = None, None, None
        for k, ci in cat.items():
            if mention[k][0] <= 0:
                continue
            sc, a, b = _local(ci, words, q, lo_bound)
            if sc <= 0:
                continue
            dist = q.i0 - b if b < q.i0 else (a - q.i1 + 1 if a >= q.i1 else 99)
            if b < q.i0 and dist > 5 or a >= q.i1 and dist > 3:
                continue
            if k in bound:
                if sc >= 1 and ci.quant and dist <= 2:
                    prev = next((e for e in exts if e.key == k), None)
                    f = (q.unit or ci.unit).factor if (q.unit or ci.unit) else 1.0
                    if prev is None or prev.lo is None or q.lo is None or abs(prev.lo - q.lo * f) > 1e-6 * max(1, abs(prev.lo)):
                        dup_key = k
                    else:
                        q.used = True
                continue
            if not ci.quant and not any(_num_eq(v.text, q.lo, q.hi) for c in ci.per_pos.values() for v in c.values) \
                    and _size_alt(ci, q) is None:
                continue
            before = b < q.i0
            dim_ok = q.unit is None or not ci.quant or (ci.unit is not None and ci.unit.dimension == q.unit.dimension) \
                or (is_count and ci.unit is None)
            if not dim_ok and not (before and dist <= 2 and sc >= 1):
                continue  # incompatible unit only binds to an explicit name right before the number
            if not ci.quant and q.unit is not None and q.unit.dimension != "size":
                continue
            pref = (sc >= 1 and before and dist <= 2, dim_ok, _adjacent(ci, nr.toks, q, lo_bound), before,
                    before or dist <= 1, sc, -dist, ci.quant == (q.unit is not None), len(ci.per_pos))
            if best is None or pref > best:
                best, best_key = pref, k
        if q.used:
            continue
        if best_key is not None:
            ci = cat[best_key]
            alt = _size_alt(ci, q)
            alt_note = (f"«размер {q.raw_value}» — обхват груди в см; российский размер = обхват / 2 = "
                        f"{U.fmt_num(alt[0])}–{U.fmt_num(alt[1])}") if alt else ""
            if ci.quant:
                e = _quant_ext(index, ci, q, order, round(0.75 + 0.2 * best[0], 2),
                               f"название характеристики «{ci.name}» рядом с числом", rng=alt)
                if alt:
                    e.status, e.reason = "corrected", alt_note + "; " + e.reason
                exts.append(e)
            else:
                lo, hi = alt or (q.lo, q.hi)
                point = lo is not None and hi is not None and abs(lo - hi) < 1e-12
                txt = U.fmt_num(lo) if point else (f"{U.fmt_num(lo)}–{U.fmt_num(hi)}" if alt else q.raw_value)
                hit = next((v.text for c in ci.per_pos.values() for v in c.values if _num_eq(v.text, lo, hi)), txt)
                exts.append(Ext(ci.key, ci.name, "qualitative", q.raw_value, q.raw_unit, q.start, q.end,
                                "corrected" if alt else "ok", 0.85,
                                (alt_note + "; " if alt else "") +
                                f"значение «{q.raw_value}» указано рядом с названием «{ci.name}»; значение КТРУ «{hit}»",
                                text=hit if point else txt, norm_text=hit if point else txt, lo=lo, hi=hi))
            bound.add(best_key)
            q.used = True
            continue
        if is_count:
            q.used = True
            continue
        if dup_key is not None:
            contradictions.append((q, cat[dup_key].name))
            q.used = True
            continue
        if q.unit is None:
            continue
        same = [k for k, ci in cat.items() if ci.quant and k not in bound and ci.unit is not None
                and ci.unit.dimension == q.unit.dimension]
        pick = None
        if len(same) == 1:
            pick, conf, how = same[0], 0.7, f"единственная характеристика с размерностью «{q.unit.dimension}» у кандидатов"
        elif len(same) > 1:
            def fits(k):
                ci = cat[k]
                tmp = _quant_ext(index, ci, q, order, 0, "")
                return sum(1 for c in ci.per_pos.values() if compat(index, c, tmp)), len(ci.per_pos)
            ranked = sorted(same, key=fits, reverse=True)
            f0, f1 = fits(ranked[0]), fits(ranked[1])
            if f0[0] > 0 and f0 > f1 and f0[1] >= 2 * f1[1]:
                pick, conf, how = ranked[0], 0.55, "наиболее распространённая характеристика с подходящей единицей"
            else:
                fit = [cat[k].name for k in ranked if fits(k)[0] > 0]
                q.choices = fit if len(fit) >= 2 else [cat[k].name for k in ranked]
        if pick:
            exts.append(_quant_ext(index, cat[pick], q, order, conf, how))
            bound.add(pick)
            q.used = True
        elif not same and q.unit.dimension not in ("size", "other") and q.lo is not None and q.lo == q.hi:
            dims_present = {ci.unit.dimension for ci in cat.values() if ci.quant and ci.unit is not None}
            if cat and q.unit.dimension not in dims_present:
                unbound.append(q)  # truly unknown: no candidate has a characteristic of this dimension

    # 3) qualitative values by lemma n-grams
    seq = [(i, lem) for i, lem in words if i not in used_tok]
    heads_q = {index.positions[c].norm_name.split()[0] for c in order[:50] if index.positions[c].norm_name}
    # words already explained by the position name or by a mentioned characteristic name are not values
    name_lem = set(index.positions[order[0]].norm_name.split()) if order else set()
    name_tok: dict[int, set[str]] = {}
    for k2, (sc2, a2, b2) in mention.items():
        if sc2 >= 1:
            ks2 = cat[k2].key_lemmas | cat[k2].name_lemmas
            for i, lem in words:
                if a2 <= i <= b2 and lem in ks2:
                    name_tok.setdefault(i, set()).add(k2)
    lem_only = [lem for _, lem in seq]
    claimed: dict[tuple[int, int], list[Ext]] = {}
    def named(s0: int, L0: int, key: str) -> bool:
        return all(name_tok.get(seq[s0 + j][0], set()) - {key} for j in range(L0))

    for k, ci in cat.items():
        if ci.quant or k in bound or ci.yes_no:
            continue
        seen = {}
        for c in ci.per_pos.values():
            for v in c.values:
                if v.vtype == "quality" and v.norm_text and v.text and v.text.strip().lower() not in (YES, NO):
                    seen.setdefault(v.norm_text, v.text)
        best = None
        for nt, txt in seen.items():
            parts = nt.split()
            L = len(parts)
            if not L or L > len(lem_only):
                continue
            for s in range(len(lem_only) - L + 1):
                if lem_only[s:s + L] == parts and not named(s, L, k):
                    cand = (L, nt, txt, s)
                    if best is None or cand[0] > best[0]:
                        best = cand
        if best is None:
            # fuzzy for single-word values (≥ 88)
            for nt, txt in seen.items():
                if " " in nt or len(nt) < 5 or nt.isdigit():
                    continue
                for s, lem in enumerate(lem_only):
                    if len(lem) >= 5 and fuzz.ratio(lem, nt) >= 88 and not named(s, 1, k):
                        best = (1, nt, txt, s)
                        break
                if best:
                    break
            if best is None:
                continue
            fuzzy = True
        else:
            fuzzy = False
        L, nt, txt, s = best
        if nt.isdigit() or set(nt.split()) <= heads_q or set(nt.split()) <= name_lem:
            continue
        t0, t1 = nr.toks[seq[s][0]], nr.toks[seq[s + L - 1][0]]
        sc = mention[k][0]
        e = Ext(k, ci.name, "qualitative", nr.text[t0.start:t1.end], None, t0.start, t1.end,
                "corrected" if fuzzy else "ok", round((0.8 if fuzzy else 0.85) + 0.1 * sc, 2),
                (f"«{nr.text[t0.start:t1.end]}» нечётко совпадает со значением КТРУ «{txt}»" if fuzzy else
                 f"«{nr.text[t0.start:t1.end]}» совпадает со значением КТРУ «{txt}» характеристики «{ci.name}»"),
                text=txt, norm_text=nt)
        claimed.setdefault((t0.start, t1.end), []).append(e)
    for span, lst in claimed.items():
        lst.sort(key=lambda e: (-mention[e.key][0], -len(cat[e.key].per_pos)))
        keep = lst[:1]
        exts.extend(keep)
        bound.update(e.key for e in keep)

    _av: list = []

    def all_vals() -> set:
        if not _av:
            _av.append({w for c2 in cat.values() for c in c2.per_pos.values() for v in c.values if v.norm_text
                        for w in v.norm_text.split()})
        return _av[0]

    # 4) value_not_allowed: char mentioned, next words form a known (lexicon) value not allowed by KTRU
    for k, ci in cat.items():
        if ci.quant or k in bound:
            continue
        sc, a, b = mention[k]
        if sc < 1:
            continue
        lex = index.value_lexicon.get(k, set())
        allowed = {v.norm_text for c in ci.per_pos.values() for v in c.values if v.norm_text}
        if not lex:
            continue
        any_val = all_vals()
        for i, lem in words:
            if i == b + 1 and lem in lex and lem not in allowed and lem not in any_val and i not in used_tok \
                    and lem not in heads_q and all(lem not in c2.key_lemmas for c2 in cat.values()):
                t = nr.toks[i]
                exts.append(Ext(k, ci.name, "qualitative", t.orig, None, t.start, t.end, "error", 0.7,
                                f"Значение «{t.orig}» не входит в перечень допустимых значений КТРУ для «{ci.name}»",
                                text=t.orig, norm_text=lem, error="value_not_allowed"))
                bound.add(k)
                break

    # 5) yes/no flags: «с подлокотниками» → Да, «без подлокотников» → Нет
    for k, ci in cat.items():
        if not ci.yes_no or k in bound:
            continue
        sc, a, b = mention[k]
        if sc < 1:
            continue
        if any(k2 in bound and k2 != k and not cat[k2].yes_no and ci.key_lemmas <= cat[k2].name_lemmas and mention[k2][1] <= b
               and a <= mention[k2][2] for k2 in cat):
            continue  # «количество выдвижных ящиков 12» is not «наличие выдвижных ящиков»
        neg = a > 0 and nr.toks[a - 1].norm == "без"
        t0 = nr.toks[a - 1] if neg else nr.toks[a]
        t1 = nr.toks[b]
        j = b + 1
        while j < len(nr.toks) and nr.toks[j].kind == "sym" and j <= b + 2:
            j += 1
        how = "отрицается предлогом «без»" if neg else "упомянут в запросе"
        if j < len(nr.toks) and nr.toks[j].norm in YES_W | NO_W:
            neg, t1 = nr.toks[j].norm in NO_W, nr.toks[j]
            how = "значение указано явно"
        val = "Нет" if neg else "Да"
        exts.append(Ext(k, ci.name, "qualitative", nr.text[t0.start:t1.end], None, t0.start, t1.end, "ok", 0.8,
                        f"«{nr.text[t0.start:t1.end]}» → {val}: признак «{ci.name}» {how}",
                        text=val, norm_text=val.lower()))
        bound.add(k)
    return exts, unbound, contradictions


def apply_overrides(index: KtruIndex, overrides, cat: dict[str, CharInfo], exts: list[Ext],
                    order: list[str]) -> list[Ext]:
    by_key = {e.key: e for e in exts}
    for o in overrides:
        k = norm(o.name)
        ci = cat.get(k) or next((c for c in cat.values() if c.name.lower() == o.name.lower()), None)
        if ci is None:
            continue
        k = ci.key
        if ci.quant:
            num = U.parse_number(o.value.split()[0]) if o.value.strip() else None
            unit = U.find_unit(index, o.unit) if o.unit else None
            if num is None:
                continue
            q = U.Quantity(num, num, unit, o.value, o.unit, None, None, -1, -1, -1)
            e = _quant_ext(index, ci, q, order, 1.0, "задано пользователем")
        else:
            nt = norm(o.value)
            txt = next((v.text for c in ci.per_pos.values() for v in c.values if v.norm_text == nt), o.value)
            e = Ext(k, ci.name, "qualitative", o.value, None, None, None, "ok", 1.0, "задано пользователем",
                    text=txt, norm_text=nt)
        e.source = "override"
        by_key[k] = e
    return list(by_key.values())
