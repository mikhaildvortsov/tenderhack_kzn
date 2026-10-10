"""Run eval in-process. cd backend && .venv/bin/python ../eval/run_eval.py [--limit N] [--kind K]"""
import argparse, difflib, glob, json, os, re, statistics, sys, time
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
EV = os.path.join(ROOT, "eval")

ap = argparse.ArgumentParser()
ap.add_argument("--limit", type=int, default=0)
ap.add_argument("--kind", default="")
args = ap.parse_args()

from app.schemas import AnalyzeRequest
from engine.lexicon import load_index
from engine.pipeline import analyze

try:
    idx = load_index()
except TypeError:
    idx = load_index(os.path.join(ROOT, "data", "build", "index.pkl"))

cases = []
for fn in sorted(glob.glob(os.path.join(EV, "cases", "*.jsonl"))):
    for line in open(fn, encoding="utf-8"):
        if line.strip():
            cases.append(json.loads(line))
if args.kind:
    cases = [c for c in cases if c["kind"] == args.kind]
if args.limit:
    by = defaultdict(list)
    for c in cases:
        by[c["kind"]].append(c)
    cases = [c for k in by for c in by[k][: args.limit]]

SYM = {}
for u in idx.okei.values():
    for s in list(u.symbols) + [u.name.lower()]:
        SYM.setdefault(s.lower(), (u.dimension, u.factor))


def split_val(s):
    s = (s or "").strip()
    m = re.match(r"^(-?\d+(?:[.,]\d+)?)\s*(.*)$", s)
    if not m:
        return None, None, s
    return float(m.group(1).replace(",", ".")), m.group(2).strip().lower() or None, s


def base(n, u):
    if u and u in SYM:
        return SYM[u][0], n * SYM[u][1]
    return None, n


def val_eq(exp, got_val, got_unit):
    en, eu, et = split_val(exp)
    if en is None:
        g = (got_val or "").lower().strip()
        e = et.lower().strip()
        return bool(g) and (g == e or e in g or g in e)
    try:
        gn = float(str(got_val).replace(",", "."))
    except Exception:
        gn, gu2, _ = split_val(str(got_val))
        if gn is None:
            return False
    ed, eb = base(en, eu)
    gd, gb = base(gn, (got_unit or "").lower() or None)
    if ed and gd and ed != gd:
        return False
    tol = 0.01 * max(abs(eb), 1e-9)
    return abs(eb - gb) <= tol


def nn(s):
    return re.sub(r"[^а-яa-z0-9 ]", "", s.lower().replace("ё", "е")).strip()


def name_eq(a, b):
    a, b = nn(a), nn(b)
    return a == b or a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75


def find_char(chars, name):
    for c in chars:
        if name_eq(c.name, name):
            yield c


results = []
errors_ct = 0
for c in cases:
    t0 = time.perf_counter()
    try:
        r = analyze(AnalyzeRequest(text=c["text"]), idx)
        err = None
    except Exception as e:
        r, err = None, repr(e)
        errors_ct += 1
    dt = (time.perf_counter() - t0) * 1000
    res = dict(case=c, ms=dt, err=err)
    if r is not None:
        cands = list(r.candidates)
        top = [r.final.code] if r.final else []
        top += [x.code for x in cands if x.code not in top]
        exp = set(c["expected_codes_any"] or ([c["expected_code"]] if c["expected_code"] else []))
        res.update(
            status=r.status, cat=r.category.id, final_name=(r.final.name if r.final else None), top=top[:5],
            cat_ok=r.category.id == c["category"],
            has_exp=bool(exp),
            top1=bool(exp) and bool(top) and top[0] in exp,
            top3=bool(exp) and any(x in exp for x in top[:3]),
            status_ok=None if c["expected_status"] in (None, "any") else r.status == c["expected_status"],
            issue_types=sorted({i.type for i in r.issues}),
            err_issue_types=sorted({i.type for i in r.issues if i.severity == "error"}),
            n_rec=len(r.recommendations),
            chars=[(x.name, x.value if x.value is not None else x.raw_value, x.unit if x.value is not None else x.raw_unit, x.status) for x in r.characteristics],
        )
        # extraction
        exp_chars = c["expected_chars"] or {}
        real = c["kind"] == "real_ste"
        got = [x for x in r.characteristics if x.raw_value is not None and x.status not in ("missing", "suggested")]
        correct, miss = 0, []
        used = set()
        for en, ev in exp_chars.items():
            ok = False
            for g in got:
                if id(g) in used or not name_eq(g.name, en):
                    continue
                if real or val_eq(ev, g.value if g.value is not None else g.raw_value, g.unit if g.value is not None else g.raw_unit):
                    ok = True
                    used.add(id(g))
                    break
            correct += ok
            if not ok:
                miss.append(en)
        res.update(ex_exp=len(exp_chars), ex_ok=correct, ex_got=len(got), ex_miss=miss)
    results.append(res)

ok = [r for r in results if r["err"] is None]


def pct(a, b):
    return round(100 * a / b, 1) if b else None


def head_match(r):
    """Heuristic: resolved on a real STE is 'plausible' if the first word stem of the KTRU name occurs in the STE text."""
    fn = (r.get("final_name") or "").lower().replace("ё", "е")
    w = re.findall(r"[а-я]+", fn)
    t = r["case"]["text"].lower().replace("ё", "е")
    return bool(w) and w[0][:5] in t


def metrics(rs):
    rs = [r for r in rs if r["err"] is None]
    m = {"n": len(rs)}
    m["category_acc"] = pct(sum(r["cat_ok"] for r in rs), len(rs))
    w = [r for r in rs if r["has_exp"]]
    m["top1"] = pct(sum(r["top1"] for r in w), len(w))
    m["top3"] = pct(sum(r["top3"] for r in w), len(w))
    s = [r for r in rs if r["status_ok"] is not None]
    m["status_acc"] = pct(sum(r["status_ok"] for r in s), len(s))
    cl = [r for r in rs if r["case"]["kind"] in ("synthetic_clean",)]
    m["clean_no_false_error"] = pct(sum(not r["err_issue_types"] for r in cl), len(cl))
    tp = fp = fn = 0
    per = defaultdict(lambda: [0, 0, 0])
    for r in rs:
        if r["case"]["kind"] == "real_ste":
            continue
        E = set(r["case"]["expected_issue_types"])
        G = set(r["issue_types"])
        for t in E | G:
            if t in E and t in G: per[t][0] += 1
            elif t in G: per[t][1] += 1
            else: per[t][2] += 1
    m["issues"] = {t: dict(tp=v[0], fp=v[1], fn=v[2], recall=pct(v[0], v[0] + v[2]), precision=pct(v[0], v[0] + v[1])) for t, v in sorted(per.items())}
    inj = [r for r in rs if r["case"]["expected_issue_types"]]
    m["injected_recall"] = pct(sum(set(r["case"]["expected_issue_types"]) <= set(r["issue_types"]) for r in inj), len(inj))
    rr = [r for r in rs if r["case"]["kind"] == "real_ste"]
    if rr:
        res_ = [r for r in rr if r["status"] == "resolved"]
        m["real_resolved_rate"] = pct(len(res_), len(rr))
        m["real_false_resolved"] = pct(sum(1 for r in res_ if not head_match(r)), len(rr))
    am = [r for r in rs if r["status"] == "ambiguous"]
    m["ambiguous_with_rec"] = pct(sum(r["n_rec"] >= 1 for r in am), len(am))
    ec = sum(r["ex_exp"] for r in rs); ek = sum(r["ex_ok"] for r in rs); eg = sum(r["ex_got"] for r in rs)
    p = ek / eg if eg else 0; rc = ek / ec if ec else 0
    m["extract"] = dict(precision=pct(ek, eg), recall=pct(ek, ec), f1=round(100 * 2 * p * rc / (p + rc), 1) if p + rc else 0)
    ms = sorted(r["ms"] for r in rs)
    if ms:
        m["latency_ms"] = dict(p50=round(statistics.median(ms), 1), p95=round(ms[min(len(ms) - 1, int(0.95 * len(ms)))], 1), max=round(ms[-1], 1))
    return m


overall = metrics(results)
byc = {k: metrics([r for r in results if r["case"]["category"] == k]) for k in ("clothing", "furniture", "tools")}
byk = {k: metrics([r for r in results if r["case"]["kind"] == k]) for k in sorted({r["case"]["kind"] for r in results})}
note_kind = lambda r: r["case"]["note"].split(":")[0]
bysub = {k: metrics([r for r in results if r["case"]["kind"] == "synthetic_noisy" and note_kind(r) == k]) for k in ("typo", "layout", "units", "out_of_range", "unit_mismatch", "incomplete")}
json.dump(dict(overall=overall, by_category=byc, by_kind=byk, by_noisy_subtype=bysub, crashes=errors_ct),
          open(os.path.join(EV, "results.json"), "w"), ensure_ascii=False, indent=1)


def brief(r):
    if r["err"]:
        return "EXC " + r["err"]
    ch = "; ".join(f"{n}={v}{(' ' + u) if u else ''}[{s}]" for n, v, u, s in r["chars"][:6])
    return f"status={r['status']} cat={r['cat']} top={r['top'][:3]} issues={r['issue_types']} rec={r['n_rec']} chars: {ch}"


def exp_s(c):
    return f"cat={c['category']} code={c['expected_code'] or c['expected_codes_any']} status={c['expected_status']} issues={c['expected_issue_types']} chars={c['expected_chars']}"


def examples(title, pred, n=10):
    xs = [r for r in ok if pred(r)]
    out = [f"### {title} ({len(xs)})\n"]
    for r in xs[:n]:
        c = r["case"]
        out.append(f"- `{c['id']}` ({c['note']})\n  - text: {c['text']}\n  - expected: {exp_s(c)}\n  - got: {brief(r)}")
    return "\n".join(out) + "\n"


def tbl(d):
    cols = ["n", "category_acc", "top1", "top3", "status_acc", "clean_no_false_error", "injected_recall", "ambiguous_with_rec", "real_resolved_rate", "real_false_resolved"]
    h = "| group | " + " | ".join(cols) + " | extract P/R/F1 | p50/p95/max ms |\n|" + "---|" * (len(cols) + 3) + "\n"
    for k, m in d.items():
        e = m["extract"]; l = m.get("latency_ms", {})
        h += f"| {k} | " + " | ".join(str(m.get(c)) for c in cols) + f" | {e['precision']}/{e['recall']}/{e['f1']} | {l.get('p50')}/{l.get('p95')}/{l.get('max')} |\n"
    return h


md = ["# Eval report\n", f"Cases: {len(cases)}, crashes: {errors_ct}\n", "## Overall\n", tbl({"ALL": overall}),
      "## By category\n", tbl(byc), "## By kind\n", tbl(byk), "## Noisy subtypes\n", tbl(bysub),
      "## Issue types (non-real cases)\n", "| type | tp | fp | fn | recall | precision |\n|---|---|---|---|---|---|\n"]
for t, v in overall["issues"].items():
    md.append(f"| {t} | {v['tp']} | {v['fp']} | {v['fn']} | {v['recall']} | {v['precision']} |\n")
md.append("\n## SC targets\nSC-001 top1>=90, top3>=97; SC-002 extract recall>=85; SC-003 injected_recall>=90 with FP<=10%; SC-004 ambiguous_with_rec>=95; SC-005 p95<2000ms.\n\n## Error examples\n")
md += [
    examples("Crashes", lambda r: r["err"]),
    examples("Wrong category", lambda r: not r["cat_ok"]),
    examples("Wrong top-1 code", lambda r: r["has_exp"] and not r["top1"]),
    examples("Code not in top-3", lambda r: r["has_exp"] and not r["top3"]),
    examples("Wrong status", lambda r: r["status_ok"] is False),
    examples("Missed injected issue", lambda r: r["case"]["expected_issue_types"] and not set(r["case"]["expected_issue_types"]) <= set(r["issue_types"])),
    examples("False error issue on clean", lambda r: r["case"]["kind"] == "synthetic_clean" and r["err_issue_types"]),
    examples("False resolved on real STE (KTRU name not in text)", lambda r: r["case"]["kind"] == "real_ste" and r["status"] == "resolved" and not head_match(r)),
    examples("Extraction miss", lambda r: r["ex_miss"]),
    examples("Ambiguous without recommendations", lambda r: r["status"] == "ambiguous" and r["n_rec"] == 0),
]
tp_path = os.path.join(EV, "top_problems.md")
if os.path.exists(tp_path):
    md.append(open(tp_path, encoding="utf-8").read())
open(os.path.join(EV, "report.md"), "w", encoding="utf-8").write("\n".join(md))
print(json.dumps(overall, ensure_ascii=False, indent=1))
print({k: (m["top1"], m["top3"], m["status_acc"], m["category_acc"]) for k, m in byk.items()})

with open(os.path.join(EV, "results_cases.jsonl"), "w", encoding="utf-8") as f:
    for r in results:
        d = {k: v for k, v in r.items() if k != "case"}
        d["id"] = r["case"]["id"]
        f.write(json.dumps(d, ensure_ascii=False, default=str) + "\n")
