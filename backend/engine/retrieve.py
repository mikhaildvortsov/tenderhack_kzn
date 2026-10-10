"""Category detection and candidate retrieval: BM25 (full position doc) fused with name similarity."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from rapidfuzz import fuzz

from engine.models import KtruIndex

CATEGORY_NAMES = {"clothing": "Одежда и обувь", "furniture": "Мебель", "tools": "Инструменты", "unknown": "Не определена"}
TOP_K = 200
W_BM25, W_NAME, W_HEAD = 0.35, 0.45, 0.2
_CACHE: dict[int, dict] = {}


@dataclass
class Retrieved:
    category: str
    category_conf: float
    category_count: int            # positions of the category in the index
    all_count: int
    ranked: list[tuple[str, float, float]]   # (code, fused score 0..1, bm25_norm), sorted, after name stage
    name_matched: int              # size after the name stage
    category_pool: int             # candidates with any lexical evidence inside the category
    weak: bool = False             # no head-noun match and low name overlap → likely not in KTRU scope


def prep(index: KtruIndex) -> dict:
    c = _CACHE.get(id(index))
    if c is None:
        codes = list(index.doc_codes)
        pos = [index.positions[k] for k in codes]
        name_sets = [frozenset(p.norm_name.split()) for p in pos]
        heads = [p.norm_name.split()[0] if p.norm_name else "" for p in pos]
        cats = np.array([p.category for p in pos])
        cat_count = {k: int((cats == k).sum()) for k in ("clothing", "furniture", "tools")}
        c = {"codes": codes, "name_sets": name_sets, "heads": heads, "cats": cats, "cat_count": cat_count,
             "names": [p.norm_name for p in pos], "head_set": set(heads)}
        _CACHE[id(index)] = c
    return c


def retrieve(index: KtruIndex, q_lemmas: list[str]) -> Retrieved:
    c = prep(index)
    n = len(c["codes"])
    if not q_lemmas:
        return Retrieved("unknown", 0.0, n, n, [], 0, 0)
    raw = np.asarray(index.bm25.get_scores(q_lemmas), dtype=float)
    qset = set(q_lemmas)
    mx = float(raw.max()) if raw.size else 0.0
    bm = raw / mx if mx > 0 else raw
    # name evidence only where the doc shares a lemma with the query (BM25>0) or the head matches
    idx = np.nonzero(raw > 0)[0].tolist()
    head_hit = [i for i, h in enumerate(c["heads"]) if h in qset]
    cand = set(idx) | set(head_hit)
    if not cand:
        return Retrieved("unknown", 0.0, n, n, [], 0, 0)
    qstr = " ".join(q_lemmas)
    scored = []
    for i in cand:
        ns = c["name_sets"][i]
        cover = len(ns & qset) / len(ns) if ns else 0.0
        fz = fuzz.token_set_ratio(qstr, c["names"][i]) / 100.0
        name_sim = 0.6 * cover + 0.4 * fz
        head = 1.0 if c["heads"][i] in qset else 0.0
        scored.append((i, W_BM25 * float(bm[i]) + W_NAME * name_sim + W_HEAD * head, float(bm[i]), head, cover))
    scored.sort(key=lambda x: -x[1])

    # category vote over top-20 (score-weighted)
    votes: dict[str, float] = {}
    voters = [x for x in scored if x[3] > 0] or scored
    for i, s, *_ in voters[:20]:
        votes[c["cats"][i]] = votes.get(c["cats"][i], 0.0) + s
    tot = sum(votes.values()) or 1.0
    cat, v = max(votes.items(), key=lambda kv: kv[1])
    conf = round(v / tot, 3)
    pool = [x for x in scored if c["cats"][x[0]] == cat]

    # name stage: head-noun matches if any, else relative score threshold
    if any(x[3] > 0 for x in pool):
        kept = [x for x in pool if x[3] > 0]
    else:
        top = pool[0][1] if pool else 0.0
        kept = [x for x in pool if x[1] >= 0.5 * top]
    kept = kept[:TOP_K]
    ranked = [(c["codes"][i], round(s, 4), round(b, 4)) for i, s, b, _, _ in kept]
    weak = not any(x[3] > 0 for x in pool) and max((x[4] for x in pool), default=0.0) < 0.5
    return Retrieved(cat, conf, c["cat_count"].get(cat, n), n, ranked, len(kept), len(pool), weak)
