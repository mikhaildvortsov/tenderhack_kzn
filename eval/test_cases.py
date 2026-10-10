"""Dataset sanity checks. Run: cd backend && .venv/bin/python -m pytest ../eval/test_cases.py -q"""
import glob, json, os
import pytest

D = os.path.join(os.path.dirname(__file__), "cases")
ROWS = [json.loads(l) for f in sorted(glob.glob(D + "/*.jsonl")) for l in open(f, encoding="utf-8") if l.strip()]
KEYS = {"id", "category", "kind", "text", "expected_code", "expected_codes_any", "expected_status", "expected_issue_types", "expected_chars", "note"}


def test_counts():
    k = [r["kind"] for r in ROWS]
    assert k.count("synthetic_clean") >= 290 and k.count("synthetic_noisy") >= 290 and k.count("real_ste") == 150


def test_unique_ids():
    assert len({r["id"] for r in ROWS}) == len(ROWS)


@pytest.mark.parametrize("r", ROWS, ids=lambda r: r["id"])
def test_row(r):
    assert KEYS <= set(r) and r["text"].strip()
    assert r["category"] in ("clothing", "furniture", "tools")
    if r["expected_status"] == "resolved":
        assert r["expected_code"]
    assert not (r["expected_code"] and r["expected_codes_any"])
