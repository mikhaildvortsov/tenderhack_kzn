"""KTRU XML (data/КТРУ/xml_all/*.xml) → SQLite data/build/ktru.sqlite (scope from etl.categories)."""
from __future__ import annotations

import glob
import json
import logging
import os
import sqlite3
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

from lxml import etree

from etl.categories import category_of

log = logging.getLogger("etl.parse_ktru")

REPO = Path(__file__).resolve().parents[2]
XML_DIR = REPO / "data" / "КТРУ" / "xml_all"
BUILD_DIR = REPO / "data" / "build"
DB_PATH = BUILD_DIR / "ktru.sqlite"

NS = "{http://zakupki.gov.ru/oos/types/1}"

SCHEMA = """
CREATE TABLE position (
  code TEXT PRIMARY KEY, version INTEGER NOT NULL, name TEXT NOT NULL,
  okpd2_code TEXT NOT NULL, okpd2_name TEXT, category TEXT NOT NULL, status TEXT NOT NULL,
  app_date_start TEXT, app_date_end TEXT, okei_codes TEXT, okei_names TEXT,
  parent_code TEXT, standards TEXT
);
CREATE TABLE characteristic (
  id INTEGER PRIMARY KEY, position_code TEXT NOT NULL REFERENCES position(code),
  code TEXT, name TEXT NOT NULL, type INTEGER, kind INTEGER, required INTEGER NOT NULL,
  choice_type INTEGER
);
CREATE TABLE char_value (
  id INTEGER PRIMARY KEY, characteristic_id INTEGER NOT NULL REFERENCES characteristic(id),
  value_code TEXT, vtype TEXT NOT NULL, text TEXT,
  min REAL, min_op TEXT, max REAL, max_op TEXT, value REAL,
  okei_code TEXT, okei_name TEXT
);
CREATE INDEX ix_char_pos ON characteristic(position_code);
CREATE INDEX ix_val_char ON char_value(characteristic_id);
"""


def _t(el, path: str) -> Optional[str]:
    v = el.findtext(NS + path.replace("/", "/" + NS))
    return v.strip() if v is not None and v.strip() else None


def _int(v: Optional[str]) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _float(v: Optional[str]) -> Optional[float]:
    try:
        return float(v.replace(",", ".")) if v is not None else None
    except ValueError:
        return None


def _parse_values(ch) -> list[dict]:
    out = []
    for v in ch.iterfind(f"{NS}values/{NS}value"):
        vcode = _t(v, "valueCode")
        okei_code, okei_name = _t(v, "OKEI/code"), _t(v, "OKEI/name")
        q = _t(v, "qualityDescription")
        if q is not None:
            out.append(dict(value_code=vcode, vtype="quality", text=q, okei_code=okei_code, okei_name=okei_name))
        for r in v.iterfind(f"{NS}rangeSet/{NS}valueRange"):
            out.append(dict(
                value_code=vcode, vtype="range",
                min=_float(_t(r, "min")), min_op=_t(r, "minMathNotation"),
                max=_float(_t(r, "max")), max_op=_t(r, "maxMathNotation"),
                okei_code=okei_code, okei_name=okei_name,
            ))
        for c in v.iterfind(f"{NS}valueSet/{NS}concreteValue"):
            out.append(dict(value_code=vcode, vtype="concrete", value=_float(c.text),
                            text=None if _float(c.text) is not None else (c.text or "").strip() or None,
                            okei_code=okei_code, okei_name=okei_name))
    return out


def _parse_position(d) -> Optional[dict]:
    okpd2 = _t(d, "OKPD2/code")
    cat = category_of(okpd2)
    if cat is None or _t(d, "status") != "ACTIVE":
        return None
    chars = []
    for ch in d.iterfind(f"{NS}characteristics/{NS}characteristic"):
        if (_t(ch, "actual") or "true").lower() == "false":
            continue
        chars.append(dict(
            code=_t(ch, "code"), name=_t(ch, "name") or "", type=_int(_t(ch, "type")),
            kind=_int(_t(ch, "kind")), required=int((_t(ch, "isRequired") or "").lower() == "true"),
            choice_type=_int(_t(ch, "choiceType")), values=_parse_values(ch),
        ))
    okeis = [(_t(o, "code"), _t(o, "name")) for o in d.iterfind(f"{NS}OKEIs/{NS}OKEI")]
    return dict(
        code=_t(d, "code"), version=_int(_t(d, "version")) or 0, name=_t(d, "name") or "",
        okpd2_code=okpd2, okpd2_name=_t(d, "OKPD2/name"), category=cat, status="ACTIVE",
        app_date_start=_t(d, "applicationDateStart"), app_date_end=_t(d, "applicationDateEnd"),
        okei_codes=[c for c, _ in okeis], okei_names=[n for _, n in okeis],
        parent_code=_t(d, "parentPositionInfo/code"),
        standards=[x.text.strip() for x in d.iterfind(f"{NS}NSI/{NS}standarts/{NS}standart/{NS}docName") if x.text],
        chars=chars,
    )


def parse_file(path: str) -> tuple[list[dict], int]:
    out, total = [], 0
    for _, el in etree.iterparse(path, events=("end",), tag=NS + "position", huge_tree=True):
        total += 1
        d = el.find(NS + "data")
        if d is not None:
            p = _parse_position(d)
            if p is not None:
                out.append(p)
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]
    return out, total


def write_sqlite(positions: list[dict], db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    cid = vid = 0
    pos_rows, ch_rows, val_rows = [], [], []
    for p in positions:
        pos_rows.append((p["code"], p["version"], p["name"], p["okpd2_code"], p["okpd2_name"], p["category"],
                         p["status"], p["app_date_start"], p["app_date_end"],
                         json.dumps(p["okei_codes"], ensure_ascii=False), json.dumps(p["okei_names"], ensure_ascii=False),
                         p["parent_code"], json.dumps(p["standards"], ensure_ascii=False)))
        for c in p["chars"]:
            cid += 1
            ch_rows.append((cid, p["code"], c["code"], c["name"], c["type"], c["kind"], c["required"], c["choice_type"]))
            for v in c["values"]:
                vid += 1
                val_rows.append((vid, cid, v.get("value_code"), v["vtype"], v.get("text"), v.get("min"), v.get("min_op"),
                                 v.get("max"), v.get("max_op"), v.get("value"), v.get("okei_code"), v.get("okei_name")))
    con.executemany("INSERT INTO position VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", pos_rows)
    con.executemany("INSERT INTO characteristic VALUES (?,?,?,?,?,?,?,?)", ch_rows)
    con.executemany("INSERT INTO char_value VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", val_rows)
    con.commit()
    con.close()
    log.info("sqlite: %d positions, %d characteristics, %d values → %s", len(pos_rows), len(ch_rows), len(val_rows), db_path)


def run(xml_dir: Path = XML_DIR, db_path: Path = DB_PATH, workers: Optional[int] = None) -> dict:
    t0 = time.time()
    files = sorted(glob.glob(str(xml_dir / "*.xml")))
    if not files:
        raise FileNotFoundError(f"no KTRU XML in {xml_dir}")
    workers = workers or min(8, os.cpu_count() or 2)
    best: dict[str, dict] = {}
    total = 0
    with Pool(workers) as pool:
        for i, (rows, n) in enumerate(pool.imap_unordered(parse_file, files), 1):
            total += n
            for p in rows:
                if p["code"] not in best or p["version"] > best[p["code"]]["version"]:
                    best[p["code"]] = p
            if i % 10 == 0 or i == len(files):
                log.info("parsed %d/%d files, %d positions seen, %d in scope", i, len(files), total, len(best))
    positions = sorted(best.values(), key=lambda p: p["code"])
    write_sqlite(positions, db_path)
    stats = {"files": len(files), "positions_total": total, "positions_scope": len(positions),
             "parse_seconds": round(time.time() - t0, 1)}
    log.info("parse done: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    run()
