"""Index loading (data/build/index.pkl) and KTRU position detail for the API."""
from __future__ import annotations

import os
import pickle
import re
import threading
from pathlib import Path
from typing import Optional, Union

from engine.models import CharRec, KtruIndex, ValueRec

REPO = Path(__file__).resolve().parents[2]
DEFAULT_INDEX_PATH = REPO / "data" / "build" / "index.pkl"

_cache: dict[str, KtruIndex] = {}
_lock = threading.Lock()

_OPS = {"greater": ">", "greaterOrEqual": "≥", "less": "<", "lessOrEqual": "≤"}
CODE_NOTE = " (код значения КТРУ)"
_CODE_NAME_RE = re.compile(r"^(тип|исполнени|класс|сорт|уровень|конус)")


def index_path(path: Union[str, Path, None] = None) -> Path:
    return Path(path or os.environ.get("KTRU_INDEX") or DEFAULT_INDEX_PATH)


def load_index(path: Union[str, Path, None] = None) -> KtruIndex:
    """Load the pickled index once per process (thread-safe); FileNotFoundError if not built."""
    p = str(index_path(path).resolve())
    idx = _cache.get(p)
    if idx is None:
        with _lock:
            idx = _cache.get(p)
            if idx is None:
                with open(p, "rb") as f:
                    idx = pickle.load(f)
                _cache[p] = idx
    return idx


def _num(x: float) -> str:
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def _unit_symbol(v: ValueRec) -> Optional[str]:
    if not v.unit_code and not v.unit_name:
        return None
    from etl.okei import unit_by_code  # lightweight, no heavy deps
    u = unit_by_code(v.unit_code)
    if u is not None and u.symbols and u.dimension not in ("other",):
        return u.symbols[0]
    return v.unit_name


def is_code_char(c: CharRec) -> bool:
    """Numeric KTRU characteristic whose unitless values are codes («Тип исполнения рукоятки: 1, 2, 3»)."""
    return c.type == 2 and bool(_CODE_NAME_RE.match(c.name.strip().lower())) and all(
        not v.unit_code and not v.unit_name for v in c.values)


def format_value(v: ValueRec, code: bool = False) -> str:
    """'Кулачок' | '100–150 мм' | '< 100 мм' | '≥ 2.5 кг' | '1.5 кг' | '1 (код значения КТРУ)' (code=True)."""
    if code and v.vtype != "quality":
        return format_value(v) + CODE_NOTE
    unit = _unit_symbol(v)
    suffix = f" {unit}" if unit else ""
    if v.vtype == "quality":
        return (v.text or "") + (suffix if unit and v.text and not v.text.endswith(unit) else "")
    if v.vtype == "concrete":
        if v.value is None:
            return (v.text or "") + suffix
        return _num(v.value) + suffix
    lo, hi = v.min, v.max
    if lo is not None and hi is not None:
        return f"{_num(lo)}–{_num(hi)}{suffix}"
    if lo is not None:
        return f"{_OPS.get(v.min_op or '', '≥')} {_num(lo)}{suffix}"
    if hi is not None:
        return f"{_OPS.get(v.max_op or '', '≤')} {_num(hi)}{suffix}"
    return v.text or ""


def position_detail(index: KtruIndex, code: str):
    """KTRU position → app.schemas.KtruPosition (None if not in index)."""
    from app.schemas import KtruCharacteristic, KtruPosition, KtruValue

    p = index.positions.get(code)
    if p is None:
        return None
    return KtruPosition(
        code=p.code, name=p.name, okpd2_code=p.okpd2_code, okpd2_name=p.okpd2_name,
        category=p.category, unit=p.unit, status="ACTIVE",
        characteristics=[
            KtruCharacteristic(
                code=c.code, name=c.name, type=c.type, kind=c.kind, required=c.required,
                values=[KtruValue(text=v.text, min=v.min, min_op=v.min_op, max=v.max, max_op=v.max_op,
                                  value=v.value, unit=_unit_symbol(v), display=format_value(v, is_code_char(c)))
                        for v in c.values],
            )
            for c in p.chars
        ],
    )
