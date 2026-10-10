"""Query normalization with offsets to the original text, keyboard layout and typo correction."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import process
from rapidfuzz.distance import DamerauLevenshtein

from app.schemas import Issue, Span, Suggestion
from engine.models import KtruIndex
from engine.text import _STOP, _morph, basic, en_to_ru_layout, lemma

_TOK_RE = re.compile(r"(\d+(?:[.,]\d+)?)|([a-z\[\];'`]*[a-z][a-z\[\];'`]*)|([а-я]+)|([×*%°\"″])")
_CACHE: dict[int, dict] = {}


@dataclass
class Tok:
    orig: str
    norm: str
    lemma: str
    kind: str                     # num | word | lat | sym
    start: int
    end: int
    num: Optional[float] = None
    layout_from: Optional[str] = None
    typo_from: Optional[str] = None

    @property
    def is_word(self) -> bool:
        return self.kind == "word"


@dataclass
class NormResult:
    text: str
    toks: list[Tok]
    normalized_text: str
    issues: list[Issue] = field(default_factory=list)

    def content_lemmas(self) -> list[str]:
        return [t.lemma for t in self.toks if t.kind == "word" and t.norm not in _STOP and len(t.norm) > 1]


def _prep(index: KtruIndex) -> dict:
    c = _CACHE.get(id(index))
    if c is None:
        by_first: dict[str, list[str]] = {}
        for w in index.vocab:
            if len(w) >= 3 and w[0].isalpha() and re.fullmatch(r"[а-я]+", w):
                by_first.setdefault(w[0], []).append(w)
        names, ktru = set(), set()
        for p in index.positions.values():
            names.update(p.norm_name.split())
            names.update(re.findall(r"[а-я]+", basic(p.name)))
            for ch in p.chars:
                ktru.update(re.findall(r"[а-я]+", basic(ch.name)))
                for v in ch.values:
                    if v.text:
                        ktru.update(re.findall(r"[а-я]+", basic(v.text)))
        ktru |= names
        ktru_first: dict[str, list[str]] = {}
        for w in ktru:
            if len(w) >= 3:
                ktru_first.setdefault(w[0], []).append(w)
        c = {"by_first": by_first, "names": names, "ktru": ktru, "ktru_first": ktru_first}
        _CACHE[id(index)] = c
    return c


def _known(index: KtruIndex, w: str) -> bool:
    return w in index.vocab or lemma(w) in index.vocab


def _max_dist(n: int) -> int:
    return 1 if n <= 5 else 2 if n <= 9 else 3


def correct_typo(index: KtruIndex, w: str) -> Optional[tuple[str, float, bool]]:
    """Closest vocab word for an unknown Cyrillic word: (word, confidence, unique)."""
    prep = _prep(index)
    md = _max_dist(len(w))
    res = None
    for pool in (prep["ktru_first"], prep["by_first"]):
        choices = [c for c in pool.get(w[0], ()) if abs(len(c) - len(w)) <= 2 and c != w]
        if choices:
            res = process.extract(w, choices, scorer=DamerauLevenshtein.distance, score_cutoff=md, limit=20)
        if res:
            break
    if not res:
        return None
    best_d = min(r[1] for r in res)
    top = [r[0] for r in res if r[1] == best_d]
    names = prep["names"]
    top.sort(key=lambda c: (c not in names, lemma(c) != c, abs(len(c) - len(w)), c))
    pick = top[0]
    unique = len(top) == 1 or (pick in names and sum(1 for c in top if c in names) == 1)
    conf = round(max(0.0, 1 - best_d / max(len(w), 1)), 2)
    return pick, conf, unique


def normalize(text: str, index: KtruIndex, ignored: set[str] | frozenset = frozenset()) -> NormResult:
    b = basic(text)
    toks: list[Tok] = []
    issues: list[Issue] = []
    for m in _TOK_RE.finditer(b):
        s, e = m.span()
        orig = text[s:e]
        if m.group(1):
            v = float(m.group(1).replace(",", "."))
            toks.append(Tok(orig, m.group(1).replace(",", "."), m.group(1), "num", s, e, num=v))
        elif m.group(2):
            toks.append(Tok(orig, m.group(2), m.group(2), "lat", s, e))
        elif m.group(3):
            w = m.group(3)
            toks.append(Tok(orig, w, lemma(w), "word", s, e))
        else:
            toks.append(Tok(orig, m.group(4), m.group(4), "sym", s, e))

    for i, t in enumerate(toks):
        if t.kind == "lat":
            prev_num = i > 0 and toks[i - 1].kind == "num"
            if len(t.norm) >= 3 and not (prev_num and len(t.norm) <= 3):
                conv = en_to_ru_layout(t.norm)
                if re.fullmatch(r"[а-яе]+", conv) and _known(index, conv):
                    iid = f"layout:{t.orig}"
                    if iid not in ignored:
                        t.layout_from, t.norm, t.lemma, t.kind = t.orig, conv, lemma(conv), "word"
                    issues.append(Issue(
                        id=iid, type="layout", severity="warning", span=Span(start=t.start, end=t.end, text=t.orig),
                        message=f"Неверная раскладка клавиатуры: «{t.orig}» → «{conv}»",
                        reason=f"Слово «{t.orig}», набранное в английской раскладке, соответствует «{conv}» "
                               f"в русской раскладке; это слово есть в словаре КТРУ.",
                        suggestion=Suggestion(replacement=conv, label=f"Заменить на «{conv}»"),
                        auto_applied=iid not in ignored))
            continue
        if t.kind != "word" or len(t.norm) < 4 or t.norm in _STOP:
            continue
        if _morph.word_is_known(t.norm) or t.norm in _prep(index)["ktru"]:
            continue
        fix = correct_typo(index, t.norm)
        if not fix:
            continue
        word, conf, unique = fix
        iid = f"typo:{t.orig}"
        auto = unique and conf >= 0.7 and iid not in ignored
        if auto:
            t.typo_from, t.norm, t.lemma = t.orig, word, lemma(word)
        issues.append(Issue(
            id=iid, type="typo", severity="warning" if auto else "info",
            span=Span(start=t.start, end=t.end, text=t.orig),
            message=f"Возможная опечатка: «{t.orig}» → «{word}»",
            reason=f"Слова «{t.orig}» нет в словаре КТРУ; ближайшее по написанию слово из наименований "
                   f"и характеристик КТРУ — «{word}» (сходство {int(conf * 100)}%).",
            suggestion=Suggestion(replacement=word, label=f"Заменить на «{word}»"),
            auto_applied=auto))

    parts: list[str] = []
    for i, t in enumerate(toks):
        if i and t.norm in ("x", "х", "×", "*") and toks[i - 1].kind == "num" and i + 1 < len(toks) and toks[i + 1].kind == "num":
            parts.append("x")
            continue
        if parts and parts[-1] == "x" and t.kind == "num":
            parts[-1] = "x" + t.norm
            parts[-2:] = ["".join(parts[-2:])]
            continue
        parts.append(t.norm)
    return NormResult(text=text, toks=toks, normalized_text=" ".join(parts), issues=issues)
