"""Shared in-memory index models. Contract between ETL (producer) and engine (consumer).

Do not change field names without updating both sides (see specs/001-ktru-autofill/data-model.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

VType = Literal["quality", "range", "concrete"]
Category = Literal["clothing", "furniture", "tools"]


@dataclass(slots=True)
class OkeiUnit:
    code: str                      # ОКЕИ code, e.g. "166"
    name: str                      # "Килограмм"
    symbols: tuple[str, ...]       # ("кг", "килограмм", "kg", ...), lowercased
    dimension: str                 # "mass" | "length" | "volume" | "power" | "count" | ... | "other"
    factor: float                  # multiplier to the dimension base unit (mass→кг, length→мм, volume→л ...)


@dataclass(slots=True)
class ValueRec:
    vtype: VType
    text: Optional[str] = None             # qualityDescription (original)
    norm_text: Optional[str] = None        # normalized/lemmatized text for matching
    min: Optional[float] = None
    min_op: Optional[str] = None           # "greater" | "greaterOrEqual"
    max: Optional[float] = None
    max_op: Optional[str] = None           # "less" | "lessOrEqual"
    value: Optional[float] = None          # concreteValue
    unit_code: Optional[str] = None        # ОКЕИ code
    unit_name: Optional[str] = None


@dataclass(slots=True)
class CharRec:
    name: str
    norm_name: str                         # normalized (lower, ё→е, lemmas joined by space)
    type: int                              # 1 quality, 2 quantity
    kind: Optional[int]                    # 1 fixed, 2 single choice, 3 multi choice
    required: bool
    code: Optional[str] = None
    values: list[ValueRec] = field(default_factory=list)


@dataclass(slots=True)
class PositionRec:
    code: str
    name: str
    okpd2_code: str
    okpd2_name: str
    category: Category
    unit: Optional[str]                    # first OKEI name of the position, e.g. "Штука"
    chars: list[CharRec] = field(default_factory=list)
    norm_name: str = ""                    # lemmatized name tokens joined by space


@dataclass
class KtruIndex:
    """Loaded once at startup from data/build/index.pkl (read-only, shared by requests)."""
    positions: dict[str, PositionRec]
    doc_codes: list[str]                   # BM25 doc order → position code
    bm25: object                           # rank_bm25.BM25Okapi over lemmatized docs
    vocab: set[str]                        # known lemmas/word forms (for typo/layout correction)
    char_synonyms: dict[str, set[str]]     # norm char name → normalized synonyms
    value_lexicon: dict[str, set[str]]     # norm char name → normalized known values
    okei: dict[str, OkeiUnit]              # ОКЕИ code → unit
    meta: dict = field(default_factory=dict)  # build info: counts per category, build time, source files
