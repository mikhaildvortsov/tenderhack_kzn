"""SQLite (data/build/ktru.sqlite) + xlsx lexicon → data/build/index.pkl (engine.models.KtruIndex).

Usage (from backend/): python -m etl.build_index [--skip-parse] [--skip-xlsx]
"""
from __future__ import annotations

import argparse
import json
import logging
import pickle
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

from engine.models import CharRec, KtruIndex, PositionRec, ValueRec
from engine.text import basic, lemmas, norm, tokens
from etl import okei, parse_ktru

log = logging.getLogger("etl.build_index")

REPO = Path(__file__).resolve().parents[2]
BUILD_DIR = REPO / "data" / "build"
DB_PATH = BUILD_DIR / "ktru.sqlite"
INDEX_PATH = BUILD_DIR / "index.pkl"
XLSX_CACHE = BUILD_DIR / "xlsx_lexicon.pkl"
READY_PATH = BUILD_DIR / "READY"


def _vocab_add(vocab: set[str], text: Optional[str]) -> None:
    if not text:
        return
    for w in tokens(text):
        if len(w) >= 3 and not w[0].isdigit():
            vocab.add(w)


def load_positions(db_path: Path = DB_PATH) -> dict[str, PositionRec]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    vals: dict[int, list[ValueRec]] = defaultdict(list)
    for r in con.execute("SELECT * FROM char_value ORDER BY id"):
        text = r["text"]
        vals[r["characteristic_id"]].append(ValueRec(
            vtype=r["vtype"], text=text, norm_text=(norm(text) or basic(text)) if text else None,
            min=r["min"], min_op=r["min_op"], max=r["max"], max_op=r["max_op"], value=r["value"],
            unit_code=r["okei_code"], unit_name=r["okei_name"],
        ))
    chars: dict[str, list[CharRec]] = defaultdict(list)
    for r in con.execute("SELECT * FROM characteristic ORDER BY id"):
        chars[r["position_code"]].append(CharRec(
            name=r["name"], norm_name=norm(r["name"]) or basic(r["name"]), type=r["type"] or 1,
            kind=r["kind"], required=bool(r["required"]), code=r["code"], values=vals.get(r["id"], []),
        ))
    positions: dict[str, PositionRec] = {}
    for r in con.execute("SELECT * FROM position ORDER BY code"):
        names = json.loads(r["okei_names"] or "[]")
        positions[r["code"]] = PositionRec(
            code=r["code"], name=r["name"], okpd2_code=r["okpd2_code"], okpd2_name=r["okpd2_name"] or "",
            category=r["category"], unit=names[0] if names else None, chars=chars.get(r["code"], []),
            norm_name=norm(r["name"]),
        )
    con.close()
    return positions


def validate(positions: dict[str, PositionRec], doc_codes: list[str]) -> None:
    """Data-quality gate: fail the build instead of shipping a broken index."""
    errors = []
    cats = Counter(p.category for p in positions.values())
    for c in ("clothing", "furniture", "tools"):
        if cats[c] < 100:
            errors.append(f"category {c}: only {cats[c]} positions")
    if len(doc_codes) != len(set(doc_codes)) or set(doc_codes) != set(positions):
        errors.append("doc_codes mismatch positions")
    bad = 0
    for p in positions.values():
        if not p.name or not p.okpd2_code:
            bad += 1
        for c in p.chars:
            if not c.name or c.type not in (1, 2):
                bad += 1
            for v in c.values:
                if v.vtype not in ("quality", "range", "concrete") or (
                        v.vtype == "range" and v.min is None and v.max is None):
                    bad += 1
    if bad > 0.01 * len(positions):
        errors.append(f"{bad} malformed records")
    if errors:
        raise ValueError("index validation failed: " + "; ".join(errors))
    log.info("validation ok: %s, %d malformed records", dict(cats), bad)


def load_xlsx_lexicon(use_cache: bool = True):
    from etl import xlsx_loader
    deps = [Path(xlsx_loader.__file__), *xlsx_loader.XLSX_DIR.glob("*.xlsx")]
    if use_cache and XLSX_CACHE.exists() and XLSX_CACHE.stat().st_mtime > max(p.stat().st_mtime for p in deps):
        with XLSX_CACHE.open("rb") as f:
            return pickle.load(f)
    lex = xlsx_loader.load(write_samples=not xlsx_loader.SAMPLES_PATH.exists())
    with XLSX_CACHE.open("wb") as f:
        pickle.dump(lex, f, protocol=pickle.HIGHEST_PROTOCOL)
    return lex


def build(skip_parse: bool = False, skip_xlsx: bool = False, out: Path = INDEX_PATH) -> KtruIndex:
    t0 = time.time()
    parse_stats = None
    if not skip_parse or not DB_PATH.exists():
        parse_stats = parse_ktru.run(db_path=DB_PATH)
    t_parse = time.time() - t0

    positions = load_positions(DB_PATH)
    log.info("loaded %d positions from sqlite", len(positions))

    doc_codes: list[str] = []
    corpus: list[list[str]] = []
    vocab: set[str] = set()
    char_synonyms: dict[str, set[str]] = defaultdict(set)
    value_lexicon: dict[str, set[str]] = defaultdict(set)
    unit_pairs: set[tuple[str, Optional[str]]] = set()
    for code, p in positions.items():
        quality = []
        seen = set()
        _vocab_add(vocab, p.name)
        _vocab_add(vocab, p.okpd2_name)
        for c in p.chars:
            _vocab_add(vocab, c.name)
            char_synonyms[c.norm_name].add(c.norm_name)
            for v in c.values:
                if v.unit_code:
                    unit_pairs.add((v.unit_code, v.unit_name))
                if v.text:
                    _vocab_add(vocab, v.text)
                    if v.norm_text:
                        value_lexicon[c.norm_name].add(v.norm_text)
                    if v.text not in seen:
                        seen.add(v.text)
                        quality.extend(lemmas(v.text))
        doc = lemmas(p.name) * 3 + lemmas(p.okpd2_name) + quality
        doc_codes.append(code)
        corpus.append(doc or ["_"])
    bm25 = BM25Okapi(corpus)
    validate(positions, doc_codes)

    xlsx_meta = {}
    if not skip_xlsx:
        lex = load_xlsx_lexicon()
        vocab |= lex.vocab
        for k, s in lex.char_synonyms.items():
            char_synonyms[k] |= s
        for k, s in lex.value_lexicon.items():
            value_lexicon[k] |= {x for x in s if x}
        xlsx_meta = {"ste_counts": lex.ste_counts, "char_names": len(lex.char_name_freq)}

    by_cat = Counter(p.category for p in positions.values())
    chars_by_cat = Counter()
    for p in positions.values():
        chars_by_cat[p.category] += len(p.chars)
    index = KtruIndex(
        positions=positions, doc_codes=doc_codes, bm25=bm25, vocab=vocab,
        char_synonyms=dict(char_synonyms), value_lexicon=dict(value_lexicon),
        okei=okei.ensure_units(unit_pairs),
        meta={
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "positions": len(positions),
            "positions_by_category": dict(by_cat), "chars_by_category": dict(chars_by_cat),
            "vocab": len(vocab), "parse": parse_stats, "xlsx": xlsx_meta,
            "source": str(parse_ktru.XML_DIR.relative_to(REPO)),
        },
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".pkl.tmp")
    with tmp.open("wb") as f:
        pickle.dump(index, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(out)
    index.meta["build_seconds"] = round(time.time() - t0, 1)
    log.info("index → %s (%.1f MB), parse %.1fs, total %.1fs, meta=%s", out, out.stat().st_size / 1e6,
             t_parse, time.time() - t0, {k: index.meta[k] for k in ("positions_by_category", "chars_by_category", "vocab")})
    return index


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-parse", action="store_true", help="reuse existing data/build/ktru.sqlite")
    ap.add_argument("--skip-xlsx", action="store_true", help="do not merge xlsx lexicon")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    build(skip_parse=args.skip_parse, skip_xlsx=args.skip_xlsx)
    from engine.lexicon import load_index
    t = time.time()
    idx = load_index(INDEX_PATH)
    log.info("load_index check: %.2fs", time.time() - t)
    READY_PATH.write_text(f"{idx.meta['positions']} positions {INDEX_PATH}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
