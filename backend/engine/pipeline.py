"""Analysis pipeline: normalize → retrieve → extract → narrow → recommend → validate."""
from __future__ import annotations

import time
from typing import Iterator, Optional, Union

from app.schemas import (AnalyzeRequest, AnalyzeResponse, Candidate, CategoryGuess, ExtractedCharacteristic,
                         NarrowingStep, Recommendation, Span)
from engine import extract as X
from engine import narrow as N
from engine import recommend as R
from engine import units as U
from engine import validate as V
from engine.models import KtruIndex
from engine.normalize import normalize
from engine.retrieve import CATEGORY_NAMES, retrieve
from engine.text import _morph

MAX_CANDIDATES = 20
MAX_ALLOWED = 30


def _allowed(index: KtruIndex, code: Optional[str], key: str) -> tuple[list[str], bool, Optional[object]]:
    if not code:
        return [], False, None
    c = next((c for c in index.positions[code].chars if c.norm_name == key), None)
    if c is None:
        return [], False, None
    u = X.char_unit(index, c)
    vals = []
    for v in c.values:
        s = U.fmt_value(v, u)
        if s and s not in vals:
            vals.append(s)
    return vals[:MAX_ALLOWED], c.required, c


def _candidate(index: KtruIndex, code: str, score: float, matched: int) -> Candidate:
    p = index.positions[code]
    return Candidate(code=code, name=p.name, okpd2_code=p.okpd2_code, okpd2_name=p.okpd2_name, unit=p.unit,
                     score=round(score, 4), matched_chars=matched, total_chars=len(p.chars))


def _char_out(index: KtruIndex, e: X.Ext, ref: Optional[str], text: str) -> ExtractedCharacteristic:
    allowed, req, _ = _allowed(index, ref, e.key)
    span = Span(start=e.start, end=e.end, text=text[e.start:e.end]) if e.start is not None and e.end is not None else None
    status = "error" if (e.error or e.conflict) else e.status
    return ExtractedCharacteristic(
        id=e.key, name=e.name, raw_value=e.raw_value, raw_unit=e.raw_unit, value=e.value_str(),
        unit=(e.unit.name if e.unit is not None else None) if e.kind == "quantitative" else None,
        value_kind=e.kind, span=span, status=status, confidence=e.confidence, reason=e.reason,
        required=req, allowed_values=allowed)


def _head_phrase(nr, qtok: set, text: str) -> tuple[Optional[str], Optional[str]]:
    """First noun of the product phrase and its adjacent genitive noun complement («набор отвёрток»)."""
    ws = [tk for i, tk in enumerate(nr.toks) if tk.kind == "word" and i not in qtok and len(tk.norm) > 1]
    for j, tk in enumerate(ws[:4]):
        p = _morph.parse(tk.norm)[0]
        if p.tag.POS != "NOUN":
            continue
        obj = None
        if j + 1 < len(ws) and text[tk.end:ws[j + 1].start].strip() == "":
            p2 = _morph.parse(ws[j + 1].norm)[0]
            if p2.tag.POS == "NOUN" and p2.tag.case == "gent":
                obj = ws[j + 1].lemma
        return tk.lemma, obj
    return None, None


def analyze_steps(req: AnalyzeRequest, index: KtruIndex) -> Iterator[Union[NarrowingStep, AnalyzeResponse]]:
    t0 = time.perf_counter()
    timings: dict[str, float] = {}

    def mark(name: str, since: float) -> float:
        now = time.perf_counter()
        timings[name] = round((now - since) * 1000, 2)
        return now

    text = req.text or ""
    ignored = set(req.ignored_issues)
    nr = normalize(text, index, ignored)
    quantities = U.parse_quantities(index, nr.toks, text)
    t = mark("normalize", t0)

    qtok = {i for q in quantities for i in range(q.i0, q.i1)}
    q_lemmas = [tk.lemma for i, tk in enumerate(nr.toks)
                if tk.kind == "word" and i not in qtok and len(tk.norm) > 1 and tk.lemma in nr.content_lemmas()]
    known = [w for w in q_lemmas if w in index.vocab or _morph.word_is_known(w)]

    def finish(resp: AnalyzeResponse) -> AnalyzeResponse:
        resp.issues = [i for i in resp.issues if i.id not in ignored]
        timings["total"] = round((time.perf_counter() - t0) * 1000, 2)
        resp.timings_ms = timings
        return resp

    if not known and not req.selected_code:
        yield finish(AnalyzeResponse(
            status="empty", text=text, normalized_text=nr.normalized_text,
            category=CategoryGuess(id="unknown", name=CATEGORY_NAMES["unknown"], confidence=0.0),
            issues=list(nr.issues), recommendations=R.empty()))
        return

    head, obj = _head_phrase(nr, qtok, text)
    r = retrieve(index, q_lemmas, head, obj)
    t = mark("retrieve", t)
    steps: list[NarrowingStep] = []
    st = N.category_step(r)
    steps.append(st)
    yield st
    head = " ".join(tk.norm for i, tk in enumerate(nr.toks) if tk.kind == "word" and tk.lemma in {
        index.positions[c].norm_name.split()[0] for c, _, _ in r.ranked[:20]})
    st = N.name_step(r, index, head)
    steps.append(st)
    yield st

    order = [c for c, _, _ in r.ranked]
    fused = {c: s for c, s, _ in r.ranked}
    cat = X.catalog(index, order + ([req.selected_code] if req.selected_code in index.positions and req.selected_code not in fused else []))
    exts, unbound, contradictions = X.extract(index, nr, quantities, order, cat)
    exts = X.apply_overrides(index, req.overrides, cat, exts, order)
    t = mark("extract", t)

    alive = order
    step_no = 3
    for st, alive in N.char_steps(index, alive, exts, cat, step_no):
        steps.append(st)
        step_no += 1
        yield st
    nres = N.rank(index, alive, fused, exts, cat, step_no, req.selected_code)
    weak = r.weak and not (req.selected_code in index.positions)
    if weak and nres.alive:
        nres.status, nres.final = "not_found", None
        nres.steps[-1].label = "Ранжирование: точного совпадения по наименованию нет — показаны ближайшие позиции"
        nres.steps[-1].after = len(nres.alive)
        nres.steps[-1].excluded_sample = []
    for st in nres.steps:
        steps.append(st)
        yield st
    t = mark("narrow", t)

    final = nres.final
    ref = final or (nres.alive[0] if nres.alive and not weak else None)
    if nres.status == "resolved" and final:
        recs = R.additions(index, final, exts) + [x for x in R.fixes(index, exts, True, cat) if x.kind == "fix"]
    elif nres.status == "ambiguous":
        recs = R.fixes(index, exts, True, cat) + R.clarify(index, nres.alive, exts)
    elif weak:
        near = list(dict.fromkeys(index.positions[c].name for c in nres.alive[:10]))[:5]
        what = " ".join(tk.orig for tk in nr.toks if tk.kind == "word" and tk.lemma in q_lemmas)
        recs = [Recommendation(id="fix:name", kind="fix", characteristic=None,
                               message=f"В КТРУ (категория «{CATEGORY_NAMES[r.category]}») нет позиции, точно "
                                       f"соответствующей «{what}». Уточните наименование или выберите ближайшую позицию",
                               options=near, expected_remaining=None)] + R.fixes(index, exts, True, cat)
    else:
        recs = R.fixes(index, exts, bool(order), cat)
    recs = recs[:R.MAX_RECS]
    t = mark("recommend", t)

    issues = list(nr.issues) + V.issues_for(index, text, exts, cat, nres.alive, unbound, contradictions, final,
                                            nres.status, bool(known), bool(order), weak)
    # characteristics: extracted + KTRU-fixed (suggested) + missing required of the reference position
    chars = [_char_out(index, e, ref, text) for e in exts]
    if ref:
        done = {e.key for e in exts}
        for c in index.positions[ref].chars:
            if c.norm_name in done:
                continue
            allowed, _, _ = _allowed(index, ref, c.norm_name)
            u = X.char_unit(index, c)
            if len(c.values) == 1 and final:
                v = c.values[0]
                quant = v.vtype != "quality"
                chars.append(ExtractedCharacteristic(
                    id=c.norm_name, name=c.name, value=U.fmt_value(v, None, with_unit=False),
                    unit=u.name if (quant and u) else None, value_kind="quantitative" if quant else "qualitative",
                    status="suggested", confidence=0.9 if final else 0.6, required=c.required, allowed_values=allowed,
                    reason=f"Значение зафиксировано в позиции КТРУ {ref} — подставлено автоматически"))
            elif c.required:
                chars.append(ExtractedCharacteristic(
                    id=c.norm_name, name=c.name, value_kind="quantitative" if c.type == 2 else "qualitative",
                    unit=u.name if u else None, status="missing", confidence=0.0, required=True, allowed_values=allowed,
                    reason=f"Обязательная характеристика позиции КТРУ {ref} «{index.positions[ref].name}»; в запросе не указана"))
    t = mark("validate", t)

    cands = [_candidate(index, c, nres.scores.get(c, 0.0), nres.matched.get(c, 0)) for c in nres.alive[:MAX_CANDIDATES]]
    yield finish(AnalyzeResponse(
        status=nres.status, text=text, normalized_text=nr.normalized_text,
        category=CategoryGuess(id=r.category, name=CATEGORY_NAMES[r.category],
                               confidence=round(r.category_conf * (0.5 if weak else 1.0), 3)),
        final=_candidate(index, final, nres.scores.get(final, 1.0), nres.matched.get(final, 0)) if final else None,
        candidates=cands, candidates_total=len(nres.alive), characteristics=chars, issues=issues,
        narrowing=steps, recommendations=recs))


def analyze(req: AnalyzeRequest, index: KtruIndex) -> AnalyzeResponse:
    last = None
    for item in analyze_steps(req, index):
        last = item
    assert isinstance(last, AnalyzeResponse)
    return last
