"""xlsx exports (data/Примеры выгрузок/*.xlsx) → synonyms, value lexicon, vocab, STE samples for eval.

Лист1: ID СТЕ | Наименование СТЕ | Модель | Производитель | Страна | Характеристики ("Название значение ед | ...")
Лист2: Конечная категория ПП | Код КПГЗ | Наименование КПГЗ | Название характеристики | Тип | Тип характеристики |
       Значения характеристики | Единица измерения | ID эталонной | Наименование эталонной | Значения эталонной
"""
from __future__ import annotations

import json
import logging
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Optional

import openpyxl

from engine.text import basic, norm, tokens

log = logging.getLogger("etl.xlsx_loader")

REPO = Path(__file__).resolve().parents[2]
XLSX_DIR = REPO / "data" / "Примеры выгрузок"
BUILD_DIR = REPO / "data" / "build"
NAMES_PATH = BUILD_DIR / "ste_char_names.json"
SAMPLES_PATH = BUILD_DIR / "ste_samples.jsonl"

FILES = {"Инструменты": "tools", "Мебель": "furniture", "Одежда": "clothing"}

_NUM_START = re.compile(r"(?:(?<=\s)|^)[-+]?\d")
_VAL_UNIT = re.compile(r"^(?P<v>.*\d)\s*(?P<u>[^\d]*)$", re.S)
_TRAIL_ZEROS = re.compile(r"(\d+)\.(\d*?)0+(?!\d)")
_RANGE_WORDS = ("до", "от", "не более", "не менее", "более", "менее", "свыше")
_NOT_SET = "(не задано)"


def _clean_num(s: str) -> str:
    return _TRAIL_ZEROS.sub(lambda m: m.group(1) + ("." + m.group(2) if m.group(2) else ""), s)


@lru_cache(maxsize=1)
def _default_names() -> dict[str, str]:
    try:
        return {n.lower(): n for n in json.loads(NAMES_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {}


def _split_value_unit(rest: str) -> tuple[str, Optional[str]]:
    rest = rest.strip()
    m = _VAL_UNIT.match(rest)
    if m and m.group("u").strip() and len(m.group("u").strip()) <= 15:
        return _clean_num(m.group("v").strip()), m.group("u").strip()
    return (_clean_num(rest) if m else rest), None


def parse_ste_characteristics(s: Optional[str], known_names: Optional[Iterable[str]] = None
                              ) -> list[tuple[str, str, Optional[str]]]:
    """'Вес 2.03000 кг | Тип замка ключевой' → [('Вес', '2.03', 'кг'), ('Тип замка', 'ключевой', None)].

    Name/value boundary: longest known characteristic name prefix (default: names learned from xlsx,
    data/build/ste_char_names.json) → first number → first capitalized word → first word.
    """
    if not s:
        return []
    if known_names is None:
        known = _default_names()
    elif isinstance(known_names, dict):
        known = known_names
    else:
        known = {n.lower(): n for n in known_names}
    out: list[tuple[str, str, Optional[str]]] = []
    for part in str(s).split("|"):
        part = re.sub(r"\s+", " ", part).strip()
        if not part or _NOT_SET in part:
            continue
        name = rest = None
        words = part.split(" ")
        for i in range(len(words) - 1, 0, -1):
            cand = " ".join(words[:i]).rstrip(":")
            if cand.lower() in known:
                name, rest = cand, " ".join(words[i:])
                break
        if name is None:
            m = _NUM_START.search(part)
            if m and m.start() > 0:
                name, rest = part[:m.start()].strip(), part[m.start():]
                for w in _RANGE_WORDS:
                    if name.lower().endswith(" " + w):
                        name, rest = name[: -len(w) - 1].strip(), w + " " + rest
                        break
            elif len(words) > 1:
                cap = next((i for i in range(1, len(words)) if words[i][:1].isupper() or words[i][:1] in "\"«"), None)
                i = cap if cap is not None else 1
                name, rest = " ".join(words[:i]), " ".join(words[i:])
            else:
                continue
        name = name.rstrip(": ").strip()
        value, unit = _split_value_unit(rest)
        if name and value:
            out.append((name, value, unit))
    return out


@dataclass
class XlsxLexicon:
    char_synonyms: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    value_lexicon: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    char_name_freq: Counter = field(default_factory=Counter)
    char_units: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    vocab: set[str] = field(default_factory=set)
    ste_counts: dict[str, int] = field(default_factory=dict)


def _rows(wb, sheet: str):
    it = wb[sheet].iter_rows(values_only=True)
    next(it, None)
    yield from it


norm = lru_cache(maxsize=None)(norm)  # 4.5M calls over ~100k distinct strings


def _add_vocab(vocab: set[str], text: str) -> None:
    for w in tokens(text):
        if len(w) >= 3 and not w[0].isdigit():
            vocab.add(w)


def load(xlsx_dir: Path = XLSX_DIR, samples_per_cat: int = 2000, seed: int = 42,
         write_samples: bool = True) -> XlsxLexicon:
    lex = XlsxLexicon()
    sheet2_names: set[str] = set()
    sheet1: dict[str, list[tuple]] = {}
    for fname, cat in FILES.items():
        path = xlsx_dir / f"{fname}.xlsx"
        if not path.exists():
            log.warning("missing %s", path)
            continue
        wb = openpyxl.load_workbook(path, read_only=True)  # shared strings parsed once per file
        for r in _rows(wb, "Лист2"):
            name = (r[3] or "").strip() if len(r) > 3 and isinstance(r[3], str) else ""
            if not name or len(name) > 120:
                continue
            sheet2_names.add(name)
            nn = norm(name)
            if not nn:
                continue
            _add_vocab(lex.vocab, name)
            ref = r[9] if len(r) > 9 and isinstance(r[9], str) else None
            if ref and ref.strip() and norm(ref) != nn:
                lex.char_synonyms[nn].add(norm(ref))
                lex.char_synonyms[norm(ref)].add(nn)
            for col in (6, 10):
                vals = r[col] if len(r) > col and isinstance(r[col], str) else None
                if vals:
                    for v in vals.split(";"):
                        v = v.strip()
                        if v and len(v) <= 80 and not v.replace(".", "").replace(",", "").isdigit():
                            lex.value_lexicon[nn].add(norm(v) or basic(v))
            if len(r) > 7 and isinstance(r[7], str) and r[7].strip():
                lex.char_units[nn][r[7].strip()] += 1
        sheet1[cat] = [r[:6] for r in _rows(wb, "Лист1") if r and r[0] is not None]
        wb.close()
        lex.ste_counts[cat] = len(sheet1[cat])
        log.info("xlsx %s: %d STE rows", fname, len(sheet1[cat]))

    # pass 1: names from numeric parts → known names; pass 2: full parse with known names
    learned: Counter = Counter()
    for rows in sheet1.values():
        for r in rows:
            for n, _, _ in parse_ste_characteristics(r[5], known_names=()):
                if any(ch.isdigit() for ch in n) or len(n) > 80:
                    continue
                learned[n] += 1
    known = sheet2_names | {n for n, c in learned.items() if c >= 3}
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    NAMES_PATH.write_text(json.dumps(sorted(known), ensure_ascii=False), encoding="utf-8")
    _default_names.cache_clear()
    known = {n.lower(): n for n in known}

    value_freq: Counter = Counter()
    parsed: dict[str, list[tuple]] = {}
    for cat, rows in sheet1.items():
        out = []
        for r in rows:
            chars = parse_ste_characteristics(r[5], known_names=known)
            out.append((r, chars))
            _add_vocab(lex.vocab, str(r[1] or ""))
            for n, v, u in chars:
                nn = norm(n)
                lex.char_name_freq[nn] += 1
                if u:
                    lex.char_units[nn][u] += 1
                elif not re.search(r"\d", v) and len(v) <= 60:
                    value_freq[(nn, v)] += 1
        parsed[cat] = out
    for (nn, v), c in value_freq.items():
        if c >= 2:
            lex.value_lexicon[nn].add(norm(v) or basic(v))
            _add_vocab(lex.vocab, v)
    for nn, c in lex.char_name_freq.items():
        if c >= 3:
            lex.vocab.update(w for w in nn.split() if len(w) >= 3 and not w[0].isdigit())

    if write_samples:
        rnd = random.Random(seed)
        with SAMPLES_PATH.open("w", encoding="utf-8") as f:
            for cat in sorted(parsed):
                items = parsed[cat]
                for r, chars in rnd.sample(items, min(samples_per_cat, len(items))):
                    f.write(json.dumps({
                        "category": cat, "id": str(r[0]), "name": str(r[1] or ""),
                        "characteristics": [{"name": n, "value": v, "unit": u} for n, v, u in chars],
                    }, ensure_ascii=False) + "\n")
        log.info("samples → %s", SAMPLES_PATH)
    lex.char_synonyms = dict(lex.char_synonyms)
    lex.value_lexicon = dict(lex.value_lexicon)
    lex.char_units = dict(lex.char_units)
    log.info("xlsx lexicon: %d synonyms, %d value lists, %d char names, %d vocab words",
             len(lex.char_synonyms), len(lex.value_lexicon), len(lex.char_name_freq), len(lex.vocab))
    return lex


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    load()
