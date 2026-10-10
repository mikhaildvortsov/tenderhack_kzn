"""Numbers, intervals, units: parsing from query tokens, OKEI resolution, conversion, KTRU value checks."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

from engine.models import KtruIndex, OkeiUnit, ValueRec

_SUP = str.maketrans({"²": "2", "³": "3", "ё": "е", "×": "x"})
# single-letter units that are also Russian prepositions/conjunctions: accepted only when not followed by a word
AMBIGUOUS = {"в", "с", "а", "н", "т", "ч", "m", "n", "s", "t", "a", "h", "l", "g"}
DIM_SEP = {"x", "х", "×", "*"}
_CACHE: dict[int, dict[str, OkeiUnit]] = {}


def norm_symbol(s: str) -> str:
    t = s.strip().lower().translate(_SUP)
    return re.sub(r"[\s.·*\-]+", "", t)


def symbol_map(index: KtruIndex) -> dict[str, OkeiUnit]:
    m = _CACHE.get(id(index))
    if m is None:
        m = {}
        units = sorted(index.okei.values(), key=lambda u: (u.code.startswith("X-"), u.code))
        for u in units:
            if u.dimension == "other":
                continue
            for s in (*u.symbols, u.name):
                m.setdefault(norm_symbol(s), u)
        _CACHE[id(index)] = m
    return m


def find_unit(index: KtruIndex, symbol: Optional[str]) -> Optional[OkeiUnit]:
    if not symbol:
        return None
    return symbol_map(index).get(norm_symbol(symbol))


def unit_of_value(index: KtruIndex, v: ValueRec) -> Optional[OkeiUnit]:
    u = index.okei.get(v.unit_code) if v.unit_code else None
    if u is None and v.unit_name:
        u = find_unit(index, v.unit_name)
        if u is None:
            for cand in index.okei.values():
                if cand.name == v.unit_name:
                    return cand
    return u


def short(u: Optional[OkeiUnit]) -> str:
    if u is None:
        return ""
    return u.symbols[0] if u.symbols else u.name


def fmt_num(x: Optional[float]) -> str:
    if x is None:
        return ""
    if math.isfinite(x) and abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.6g}"


def convert(value: float, a: Optional[OkeiUnit], b: Optional[OkeiUnit]) -> Optional[float]:
    if a is None or b is None:
        return None
    if a.code == b.code:
        return value
    if a.dimension != b.dimension or a.dimension == "other":
        return None
    return value * a.factor / b.factor


def parse_number(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


@dataclass
class Quantity:
    lo: Optional[float]                    # None for "до N"
    hi: Optional[float]                    # None for "от N"
    unit: Optional[OkeiUnit]
    raw_value: str
    raw_unit: Optional[str]
    start: int                             # span in original text
    end: int
    i0: int                                # token indices [i0, i1)
    i1: int
    num_i: int                             # index of the (first) number token
    dims: list[float] = field(default_factory=list)   # AxBxC → [A, B, C]
    used: bool = False

    @property
    def point(self) -> Optional[float]:
        if self.lo is not None and self.hi is not None and abs(self.lo - self.hi) < 1e-12:
            return self.lo
        return None

    def display(self) -> str:
        u = f" {self.raw_unit}" if self.raw_unit else ""
        return f"{self.raw_value}{u}"


_GAP_OK = {"", "·", "/", "-", "."}


def _unit_at(index: KtruIndex, toks, j: int, text: str):
    """Longest unit starting at token j (adjacent tokens only, max 3). Returns (unit, next_j, raw)."""
    n = len(toks)
    if j >= n or toks[j].kind == "num":
        return None, j, None
    if j > 0 and any(ch in text[toks[j - 1].end:toks[j].start] for ch in ",;"):
        return None, j, None  # «сорт 1, размер …»: a unit never follows the number across a comma
    m = symbol_map(index)
    best = None
    for k in range(j, min(j + 3, n)):
        if k > j and text[toks[k - 1].end:toks[k].start] not in _GAP_OK:
            break
        raw = text[toks[j].start:toks[k].end]
        u = m.get(norm_symbol(raw))
        if u is None and k == j:
            u = m.get(norm_symbol(toks[j].norm))
        if u is not None:
            best = (u, k + 1, raw)
    if best is None:
        return None, j, None
    u, nj, raw = best
    if nj - j == 1 and norm_symbol(raw) in AMBIGUOUS and nj < n and toks[nj].kind == "word":
        return None, j, None
    return best


_RANGE_DASH = re.compile(r"^\s*[-–—]\s*$")
_PREFIX_MAX = {"до", "менее", "не более", "небол", "максимум", "max"}
_PREFIX_MIN = {"от", "более", "свыше", "не менее", "минимум", "min"}


def parse_quantities(index: KtruIndex, toks, text: str) -> list[Quantity]:
    """toks: list of normalize.Tok (kind, norm, start, end, orig). text: original text."""
    out: list[Quantity] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t.kind != "num" or t.num is None:
            i += 1
            continue
        # part of an alphanumeric code (2MILY, С-2.002, Р6М5): not a measurement
        if i > 0 and toks[i - 1].kind in ("word", "lat") and text[toks[i - 1].end:t.start] in ("", "-") \
                and not toks[i - 1].norm in ("x", "х"):
            i += 1
            continue
        if i + 1 < n and toks[i + 1].kind in ("word", "lat") and toks[i + 1].start == t.end \
                and _unit_at(index, toks, i + 1, text)[0] is None and toks[i + 1].norm not in DIM_SEP:
            i += 1
            continue
        i0 = i
        vals = [t.num]
        raws = [t.orig]
        j = i + 1
        is_dims = False
        # AxBxC
        while j + 1 < n and toks[j].norm in DIM_SEP and toks[j + 1].kind == "num" and toks[j + 1].num is not None:
            vals.append(toks[j + 1].num)
            raws.append(toks[j + 1].orig)
            j += 2
            is_dims = True
        lo = hi = vals[0]
        rng = False
        if not is_dims:
            # N-M / N до M / от N до M
            if j < n and toks[j].kind == "num" and toks[j].num is not None and _RANGE_DASH.match(text[toks[j - 1].end:toks[j].start]):
                hi = toks[j].num
                raws.append(toks[j].orig)
                j += 1
                rng = True
            elif j + 1 < n and toks[j].norm == "до" and toks[j + 1].kind == "num" and toks[j + 1].num is not None:
                hi = toks[j + 1].num
                raws.append(toks[j + 1].orig)
                j += 2
                rng = True
        unit, nj, raw_unit = _unit_at(index, toks, j, text) if j < n else (None, j, None)
        start = t.start
        if not rng and i0 >= 1:
            p1 = toks[i0 - 1].norm
            p2 = f"{toks[i0 - 2].norm} {p1}" if i0 >= 2 else ""
            if p1 in _PREFIX_MAX or p2 in _PREFIX_MAX:
                lo = None
                i0 -= 2 if p2 in _PREFIX_MAX else 1
                start = toks[i0].start
            elif p1 in _PREFIX_MIN or p2 in _PREFIX_MIN:
                hi = None
                i0 -= 2 if p2 in _PREFIX_MIN else 1
                start = toks[i0].start
        elif rng and i0 >= 1 and toks[i0 - 1].norm == "от":
            i0 -= 1
            start = toks[i0].start
        end_i = nj if unit is not None else j
        end = toks[end_i - 1].end
        raw_value = text[t.start:toks[j - 1].end]
        if is_dims:
            q = Quantity(vals[0], vals[0], unit, raw_value, raw_unit, start, end, i0, end_i, i, dims=vals)
        else:
            q = Quantity(lo, hi, unit, raw_value, raw_unit, start, end, i0, end_i, i)
        out.append(q)
        i = end_i
    return out


# ---------- KTRU value checks ----------

def in_value(x: float, v: ValueRec, tol: float = 1e-6) -> bool:
    if v.vtype == "concrete":
        return v.value is not None and abs(x - v.value) <= tol * max(1.0, abs(v.value))
    if v.vtype == "range":
        if v.min is not None:
            if v.min_op == "greater" and not x > v.min + tol * 0:
                return False
            if x < v.min - tol * max(1.0, abs(v.min)):
                return False
        if v.max is not None:
            if v.max_op == "less" and not x < v.max:
                return False
            if x > v.max + tol * max(1.0, abs(v.max)):
                return False
        return True
    if v.vtype == "quality" and v.text:
        p = parse_number(v.text)
        return p is not None and abs(p - x) <= tol * max(1.0, abs(p))
    return False


def interval_hits(lo: Optional[float], hi: Optional[float], v: ValueRec) -> bool:
    """Query interval [lo, hi] (None = open) intersects allowed value."""
    if lo is not None and hi is not None and abs(lo - hi) < 1e-12:
        return in_value(lo, v)
    if v.vtype == "concrete" and v.value is not None:
        return (lo is None or v.value >= lo) and (hi is None or v.value <= hi)
    if v.vtype == "range":
        vmin = v.min if v.min is not None else -math.inf
        vmax = v.max if v.max is not None else math.inf
        qlo = lo if lo is not None else -math.inf
        qhi = hi if hi is not None else math.inf
        return qlo <= vmax and vmin <= qhi
    return False


def fmt_value(v: ValueRec, unit: Optional[OkeiUnit] = None, with_unit: bool = True) -> str:
    """Human display of a KTRU value: '0.4–0.6 кг', '≥ 2.5 кг', '< 0.1 кг', 'Сталь', '18 В'."""
    us = f" {short(unit)}" if unit is not None else (f" {v.unit_name}" if v.unit_name else "")
    if not with_unit:
        us = ""
    if v.vtype == "quality":
        return v.text or ""
    if v.vtype == "concrete":
        return f"{fmt_num(v.value)}{us}"
    if v.min is not None and v.max is not None:
        return f"{fmt_num(v.min)}–{fmt_num(v.max)}{us}"
    if v.min is not None:
        return f"{'>' if v.min_op == 'greater' else '≥'} {fmt_num(v.min)}{us}"
    if v.max is not None:
        return f"{'<' if v.max_op == 'less' else '≤'} {fmt_num(v.max)}{us}"
    return ""


def bounds(values: list[ValueRec]) -> tuple[Optional[float], Optional[float], bool, bool]:
    """Overall numeric span of allowed values: (min, max, min_open, max_open) — open means unbounded."""
    lo, hi = math.inf, -math.inf
    lo_open = hi_open = False
    for v in values:
        if v.vtype == "concrete" and v.value is not None:
            lo, hi = min(lo, v.value), max(hi, v.value)
        elif v.vtype == "range":
            if v.min is None:
                lo_open = True
            else:
                lo = min(lo, v.min)
            if v.max is None:
                hi_open = True
            else:
                hi = max(hi, v.max)
    return (None if lo == math.inf else lo, None if hi == -math.inf else hi, lo_open, hi_open)
