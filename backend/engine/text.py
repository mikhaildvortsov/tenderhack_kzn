"""Shared text normalization used by both ETL (index build) and engine (queries)."""
from __future__ import annotations

import re
from functools import lru_cache

import pymorphy3

_morph = pymorphy3.MorphAnalyzer()

_TOKEN_RE = re.compile(r"[a-zа-я0-9]+(?:[.,][0-9]+)?", re.IGNORECASE)
_STOP = {
    "и", "в", "во", "на", "с", "со", "для", "по", "из", "к", "о", "об", "от", "до", "не", "или",
    "а", "у", "за", "при", "без", "под", "над", "the", "of", "шт",
}

EN2RU = dict(zip(
    "qwertyuiop[]asdfghjkl;'zxcvbnm,.`",
    "йцукенгшщзхъфывапролджэячсмитьбюё",
))


def basic(text: str) -> str:
    """Lowercase, ё→е, unify quotes/dashes/spaces. Keeps string length-compatible enough for display."""
    t = text.lower().replace("ё", "е")
    t = t.replace("«", '"').replace("»", '"').replace("–", "-").replace("—", "-").replace(" ", " ")
    return t


def tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(basic(text))


@lru_cache(maxsize=200_000)
def lemma(word: str) -> str:
    if not word or word[0].isdigit() or not re.search("[а-я]", word):
        return word
    return _morph.parse(word)[0].normal_form.replace("ё", "е")


def lemmas(text: str, drop_stop: bool = True) -> list[str]:
    return [lemma(w) for w in tokens(text) if not (drop_stop and w in _STOP)]


def norm(text: str) -> str:
    """Canonical comparable form: lemmas joined by single space."""
    return " ".join(lemmas(text))


def en_to_ru_layout(word: str) -> str:
    return "".join(EN2RU.get(ch, ch) for ch in word.lower())
