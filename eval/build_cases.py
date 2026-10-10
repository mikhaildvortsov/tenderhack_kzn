"""Build eval cases -> eval/cases/*.jsonl (seed=42). Run: cd backend && .venv/bin/python ../eval/build_cases.py"""
import json, os, re, random, sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
OUT = os.path.join(ROOT, "eval", "cases")
os.makedirs(OUT, exist_ok=True)
rng = random.Random(42)

import sqlite3
from types import SimpleNamespace
from engine.models import PositionRec, CharRec, ValueRec

UNAME = {"Миллиметр": "мм", "Сантиметр": "см", "Штука": "шт", "Килограмм": "кг", "Ватт": "Вт", "Метр": "м",
         "Дюйм (25,4 мм)": "дюйм", "Ампер": "А", "Вольт": "В", "Оборот в минуту": "об/мин", "Квадратный миллиметр": "мм2",
         "Ампер-час (3,6 кКл)": "А·ч", "Грамм": "г", "Градус Цельсия": "°C", "Километр; тысяча метров": "км",
         "Литр; кубический дециметр": "л", "Секунда": "с", "Час": "ч", "Минута": "мин", "Киловатт": "кВт",
         "Гигабайт": "Гб", "Паскаль": "Па", "Кубический метр в час": "м3/ч"}


def load_from_sqlite():
    db = sqlite3.connect(os.path.join(ROOT, "data", "build", "ktru.sqlite"))
    poss = {}
    for code, name, okn, okname, cat in db.execute("select code,name,okpd2_code,okpd2_name,category from position"):
        poss[code] = PositionRec(code, name, okn, okname or "", cat, None, [], name.lower().replace("ё", "е"))
    cmap = {}
    for id_, pc, name, typ, kind, req in db.execute("select id,position_code,name,type,kind,required from characteristic"):
        if pc in poss:
            c = CharRec(name, name.lower().replace("ё", "е"), typ, kind, bool(req))
            poss[pc].chars.append(c)
            cmap[id_] = c
    for cid, vt, text, mn, mno, mx, mxo, v, oc, on in db.execute(
            "select characteristic_id,vtype,text,min,min_op,max,max_op,value,okei_code,okei_name from char_value"):
        if cid in cmap:
            cmap[cid].values.append(ValueRec(vt, text, None, mn, mno, mx, mxo, v, oc, on))
    vocab = set()
    for p in poss.values():
        vocab.update(w.lower() for w in re.findall(r"[А-Яа-яЁё]+", p.name))
        for c in p.chars:
            vocab.update(w.lower() for w in re.findall(r"[А-Яа-яЁё]+", c.name))
            for r in c.values:
                if r.text:
                    vocab.update(w.lower() for w in re.findall(r"[А-Яа-яЁё]+", r.text))
    return SimpleNamespace(positions=poss, vocab=vocab, okei={})


idx = load_from_sqlite()

CATS = ["clothing", "furniture", "tools"]
RU = "йцукенгшщзхъфывапролджэячсмитьбю"
EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
L2E = dict(zip(RU, EN))
UNIT_ALT = {"кг": [("г", 1000)], "г": [("кг", 0.001)], "мм": [("см", 0.1), ("м", 0.001)],
            "см": [("мм", 10)], "м": [("мм", 1000), ("см", 100)], "л": [("мл", 1000)], "мл": [("л", 0.001)]}
MASS = {"кг", "г", "т"}


def fmt(x):
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return ("%.4f" % x).rstrip("0").rstrip(".").replace(",", ".")


def sym(unit_code, unit_name):
    return UNAME.get(unit_name) or (unit_name or "").lower() or None


def inside(v, r):
    if r.vtype != "range":
        return False
    if r.min is not None and (v < r.min or (r.min_op == "greater" and v == r.min)):
        return False
    if r.max is not None and (v > r.max or (r.max_op == "less" and v == r.max)):
        return False
    return True


def val_ok(r, sel):
    if sel["vtype"] == "quality":
        return r.vtype == "quality" and (r.text or "").lower() == sel["text"].lower()
    if r.unit_code and sel["unit_code"] and r.unit_code != sel["unit_code"]:
        return False
    if sel["vtype"] == "concrete":
        return r.vtype == "concrete" and r.value is not None and abs(r.value - sel["num"]) < 1e-9
    return inside(sel["num"], r)


def compat(pos, sels):
    for s in sels:
        ok = False
        for c in pos.chars:
            if c.norm_name == s["norm_name"] and any(val_ok(r, s) for r in c.values):
                ok = True
                break
        if not ok:
            return False
    return True


def pick_value(c):
    rs = [r for r in c.values if (r.vtype == "quality" and r.text and len(r.text) <= 40) or r.vtype in ("range", "concrete")]
    if not rs:
        return None
    r = rng.choice(rs)
    if r.vtype == "quality":
        return dict(name=c.name, norm_name=c.norm_name, vtype="quality", text=r.text.strip(), num=None, unit=None, unit_code=None)
    if r.vtype == "concrete":
        if r.value is None:
            return None
        return dict(name=c.name, norm_name=c.norm_name, vtype="concrete", text=None, num=r.value,
                    unit=sym(r.unit_code, r.unit_name), unit_code=r.unit_code)
    lo = r.min if r.min is not None else (0 if r.max is None else r.max * 0.3)
    hi = r.max if r.max is not None else lo * 2 + 10
    if hi <= lo:
        return None
    for _ in range(20):
        v = lo + (hi - lo) * rng.uniform(0.2, 0.8)
        v = round(v, 0 if (hi - lo > 20 or r.unit_name == "Штука") else (1 if hi - lo > 2 else 2))
        if inside(v, r):
            return dict(name=c.name, norm_name=c.norm_name, vtype="range", text=None, num=v,
                        unit=sym(r.unit_code, r.unit_name), unit_code=r.unit_code)
    return None


def valstr(s, num=None, unit="keep"):
    if s["vtype"] == "quality":
        return s["text"]
    n = s["num"] if num is None else num
    u = s["unit"] if unit == "keep" else unit
    return fmt(n) + (" " + u if u else "")


def phrase(s, num=None, unit="keep"):
    v = valstr(s, num, unit)
    if s["vtype"] == "quality":
        return f"{s['name'].lower()}: {v}"
    return f"{s['name'].lower()} {v}"


def mutate_word(w):
    ops = rng.choice(["sub", "swap", "del"])
    i = rng.randrange(1, len(w) - 2)
    if ops == "sub":
        return w[:i] + rng.choice("аеиоуыэюябвгдклмнпрст".replace(w[i], "")) + w[i + 1:]
    if ops == "swap":
        return w[:i] + w[i + 1] + w[i] + w[i + 2:]
    return w[:i] + w[i + 1:]


by_norm = defaultdict(list)
for p in idx.positions.values():
    by_norm[p.norm_name].append(p.code)


def base_case(pos, nchars=None):
    cs = [c for c in pos.chars if c.values]
    rng.shuffle(cs)
    sels = []
    for c in cs:
        if len(sels) >= (nchars or rng.randint(1, 3)):
            break
        s = pick_value(c)
        if s and all(s["norm_name"] != x["norm_name"] for x in sels):
            sels.append(s)
    if not sels:
        return None
    return sels


def base_unique(pos, nchars=None, tries=12, greedy=False):
    if greedy:
        cs = [c for c in pos.chars if c.values]
        sels = []
        for _ in range(6):
            best = None
            for c in cs:
                if any(c.norm_name == x["norm_name"] for x in sels):
                    continue
                for _t in range(2):
                    sv = pick_value(c)
                    if sv:
                        n = len(exp_codes(pos, sels + [sv]))
                        if best is None or n < best[0]:
                            best = (n, sv)
            if not best:
                break
            sels.append(best[1])
            if best[0] == 1:
                break
        return sels or None
    best = None
    for _ in range(tries):
        sels = base_case(pos, nchars)
        if not sels:
            continue
        best = best or sels
        if len(exp_codes(pos, sels)) == 1:
            return sels
    return best


def exp_codes(pos, sels):
    same = [idx.positions[c] for c in by_norm[pos.norm_name]]
    ok = sorted(p.code for p in same if compat(p, sels))
    if pos.code not in ok:
        ok.append(pos.code)
    return ok


def mk(id_, pos, kind, text, sels_for_expect, status, codes, issues, note, exp_chars=None):
    ec = exp_chars if exp_chars is not None else {s["name"]: valstr(s) for s in sels_for_expect}
    return dict(id=id_, category=pos.category, kind=kind, text=text,
                expected_code=pos.code if len(codes) == 1 else None,
                expected_codes_any=codes if len(codes) > 1 else None,
                expected_status=status, expected_issue_types=issues, expected_chars=ec, note=note)


def pos_pool(cat, need_shared=False):
    ps = [p for p in idx.positions.values() if p.category == cat and any(c.values for c in p.chars)]
    if need_shared:
        ps = [p for p in ps if len(by_norm[p.norm_name]) >= 2]
    rng.shuffle(ps)
    return ps


def render(pos, sels, name=None, drop=False):
    nm = name or pos.name
    if drop:
        ws = nm.split()
        if len(ws) >= 4:
            ws.pop(rng.randrange(len(ws)))
            nm = " ".join(ws)
    return ", ".join([nm] + [phrase(s) for s in sels])


clean, noisy = [], []
for cat in CATS:
    pool = pos_pool(cat)
    n = 0
    for pos in pool:
        if n >= 100:
            break
        sels = base_unique(pos, greedy=True) if n % 3 == 0 else base_case(pos)
        if not sels:
            continue
        drop = rng.random() < 0.1
        codes = exp_codes(pos, sels)
        st = "resolved" if len(codes) == 1 else "ambiguous"
        if drop:
            st = None
        clean.append(mk(f"clean-{cat}-{n:03d}", pos, "synthetic_clean", render(pos, sels, drop=drop), sels, st, codes, [],
                        "drop_word" if drop else ("exact" if len(sels) <= 3 else "exact_full")))
        n += 1

    pool = pos_pool(cat)
    shared = pos_pool(cat, True)
    kinds = (["typo"] * 20 + ["layout"] * 15 + ["units"] * 20 + ["out_of_range"] * 15 + ["unit_mismatch"] * 15 + ["incomplete"] * 15)
    pi = 0
    si = 0
    for ki, k in enumerate(kinds):
        for _ in range(200):
            if k == "incomplete":
                if si >= len(shared):
                    si = 0
                pos = shared[si]; si += 1
                codes = sorted(by_norm[pos.norm_name])
                c = mk(f"noisy-{cat}-{ki:03d}", pos, "synthetic_noisy", pos.name, [], "ambiguous", codes, [], "incomplete", exp_chars={})
                c["note"] = "incomplete:title_only"
                c["expect_recommendations"] = True
                noisy.append(c)
                break
            pos = pool[pi % len(pool)]; pi += 1
            sels = base_unique(pos, rng.randint(1, 2), 6)
            if not sels:
                continue
            nums = [s for s in sels if s["vtype"] != "quality" and s["unit"]]
            codes = exp_codes(pos, sels)
            st = "resolved" if len(codes) == 1 else "ambiguous"
            name = pos.name
            parts = None
            if k == "typo":
                ws = [w for w in name.split() if len(w) >= 5 and w.isalpha()]
                if not ws:
                    continue
                w = rng.choice(ws)
                for _ in range(10):
                    m = mutate_word(w.lower())
                    if m not in idx.vocab:
                        break
                else:
                    continue
                text = render(pos, sels, name=name.replace(w, m, 1))
                c = mk(f"noisy-{cat}-{ki:03d}", pos, "synthetic_noisy", text, sels, st, codes, ["typo"], f"typo:{w}->{m}")
            elif k == "layout":
                ws = [w for w in name.split() if len(w) >= 4 and w.isalpha() and w.lower() == w]
                if not ws:
                    continue
                w = rng.choice(ws)
                lw = "".join(L2E.get(ch, ch) for ch in w)
                c = mk(f"noisy-{cat}-{ki:03d}", pos, "synthetic_noisy", render(pos, sels, name=name.replace(w, lw, 1)), sels, st, codes, ["layout"], f"layout:{w}->{lw}")
            else:
                if not nums:
                    continue
                t = rng.choice(nums)
                if k == "units":
                    if t["unit"] not in UNIT_ALT:
                        continue
                    nu, f = rng.choice(UNIT_ALT[t["unit"]])
                    nv = t["num"] * f
                    text = ", ".join([name] + [phrase(s, nv, nu) if s is t else phrase(s) for s in sels])
                    c = mk(f"noisy-{cat}-{ki:03d}", pos, "synthetic_noisy", text, sels, st, codes, [], f"units:{t['unit']}->{nu}")
                elif k == "out_of_range":
                    ch = next(x for x in pos.chars if x.norm_name == t["norm_name"])
                    nv = t["num"] * 10
                    if any(inside(nv, r) or (r.vtype == "concrete" and r.value == nv) for r in ch.values):
                        continue
                    text = ", ".join([name] + [phrase(s, nv) if s is t else phrase(s) for s in sels])
                    ec = {s["name"]: valstr(s) for s in sels if s is not t}
                    c = mk(f"noisy-{cat}-{ki:03d}", pos, "synthetic_noisy", text, sels, None, codes, ["out_of_range"], f"out_of_range:{t['name']}={fmt(nv)}", exp_chars=ec)
                else:
                    bad = "м" if t["unit"] in MASS else "кг"
                    text = ", ".join([name] + [phrase(s, None, bad) if s is t else phrase(s) for s in sels])
                    ec = {s["name"]: valstr(s) for s in sels if s is not t}
                    c = mk(f"noisy-{cat}-{ki:03d}", pos, "synthetic_noisy", text, sels, None, codes, ["unit_mismatch"], f"unit_mismatch:{t['name']} {t['unit']}->{bad}", exp_chars=ec)
            noisy.append(c)
            break

real = []
sp = os.path.join(ROOT, "data", "build", "ste_samples.jsonl")


def xlsx_samples():
    import openpyxl
    names = set(n.lower() for n in json.load(open(os.path.join(ROOT, "data", "build", "ste_char_names.json"), encoding="utf-8")))
    by = defaultdict(list)
    d = os.path.join(ROOT, "data", "Примеры выгрузок")
    for cat, fn in [("clothing", "Одежда"), ("furniture", "Мебель"), ("tools", "Инструменты")]:
        ws = openpyxl.load_workbook(os.path.join(d, fn + ".xlsx"), read_only=True)["Лист1"]
        for i, row in enumerate(ws.iter_rows(min_row=2, max_row=4000, values_only=True)):
            if not row[1] or len(str(row[1])) < 5:
                continue
            chars = []
            for seg in str(row[5] or "").split(" | "):
                w = seg.split(" ")
                for k in range(min(len(w) - 1, 8), 0, -1):
                    if " ".join(w[:k]).lower() in names:
                        val = " ".join(w[k:]).strip()
                        m = re.match(r"^(-?\d+(?:\.\d+)?)\s+(\S+)$", val)
                        if "не задано" in val or re.match(r"^0(\.0+)?(\s|$)", val):
                            break
                        if m:
                            v = float(m.group(1))
                            val_s, unit = (str(int(v)) if v == int(v) else str(v)), m.group(2)
                        else:
                            val_s, unit = val, None
                        if len(val_s) <= 40:
                            chars.append(dict(name=" ".join(w[:k]), value=val_s, unit=unit))
                        break
            by[cat].append(dict(id=row[0], name=str(row[1]).strip(), category=cat, characteristics=chars))
    return by


if True:
    by = defaultdict(list)
    if os.path.exists(sp):
        for line in open(sp, encoding="utf-8"):
            r = json.loads(line)
            if r.get("name"):
                by[r["category"]].append(r)
    else:
        by = xlsx_samples()
    for cat in CATS:
        rows = by.get(cat, [])
        rng.shuffle(rows)
        for i, r in enumerate(rows[:50]):
            chars = [c for c in r.get("characteristics", []) if c.get("name") and c.get("value")]
            use = rng.sample(chars, min(len(chars), rng.randint(0, 2))) if chars and rng.random() < 0.6 else []
            ph = []
            ec = {}
            for c in use:
                v = str(c["value"]) + (" " + c["unit"] if c.get("unit") else "")
                ph.append(f"{c['name'].lower()}: {v}")
                ec[c["name"]] = v
            real.append(dict(id=f"real-{cat}-{i:03d}", category=cat, kind="real_ste", text=", ".join([r["name"]] + ph),
                             expected_code=None, expected_codes_any=None, expected_status=None, expected_issue_types=[],
                             expected_chars=ec, note=f"ste_id={r.get('id')}"))

for name, rows in [("synthetic_clean", clean), ("synthetic_noisy", noisy), ("real_ste", real)]:
    with open(os.path.join(OUT, name + ".jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(name, len(rows))


def validate():
    """Dataset quality gates (completeness, uniqueness, validity, consistency)."""
    seen, bad = set(), []
    for rows in (clean, noisy, real):
        for r in rows:
            if r["id"] in seen: bad.append(("dup id", r["id"]))
            seen.add(r["id"])
            if not r["text"].strip(): bad.append(("empty text", r["id"]))
            if r["category"] not in CATS: bad.append(("bad cat", r["id"]))
            for c in ([r["expected_code"]] if r["expected_code"] else []) + (r["expected_codes_any"] or []):
                if c not in idx.positions or idx.positions[c].category != r["category"]: bad.append(("bad code", r["id"]))
            if r["expected_status"] == "resolved" and not r["expected_code"]: bad.append(("resolved w/o code", r["id"]))
            if r["expected_status"] == "ambiguous" and r["kind"] == "synthetic_clean" and not r["expected_codes_any"]: bad.append(("ambiguous w/o set", r["id"]))
            if r["kind"] == "synthetic_noisy" and r["note"].split(":")[0] in ("typo", "layout", "out_of_range", "unit_mismatch") and not r["expected_issue_types"]: bad.append(("no issue", r["id"]))
    texts = [r["text"] for rows in (clean, noisy) for r in rows]
    print("duplicate texts:", len(texts) - len(set(texts)))
    assert not bad, bad[:10]
    print("validation OK")


validate()
