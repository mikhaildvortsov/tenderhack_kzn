import pytest

from engine.normalize import normalize
from tests.fixtures.mini_index import build_mini_index


@pytest.fixture(scope="module")
def idx():
    return build_mini_index()


def test_offsets_point_to_original(idx):
    text = "Молоток  СЛЕСАРНЫЙ 0,5 кг"
    r = normalize(text, idx)
    for t in r.toks:
        assert text[t.start:t.end] == t.orig
    assert "0.5" in r.normalized_text and "молоток" in r.normalized_text


def test_typo(idx):
    r = normalize("молатак 500г", idx)
    (iss,) = [i for i in r.issues if i.type == "typo"]
    assert iss.suggestion.replacement == "молоток" and iss.auto_applied
    assert iss.span.text == "молатак" and iss.id == "typo:молатак"
    assert r.toks[0].lemma == "молоток"


def test_layout(idx):
    r = normalize("vjkjnjr", idx)
    (iss,) = r.issues
    assert iss.type == "layout" and iss.suggestion.replacement == "молоток"
    assert r.toks[0].norm == "молоток"


def test_ignored_typo_not_applied(idx):
    r = normalize("молатак", idx, ignored={"typo:молатак"})
    assert r.toks[0].norm == "молатак"


def test_known_words_untouched(idx):
    r = normalize("стол офисный", idx)
    assert not r.issues


def test_glued_number_unit_normalized(idx):
    assert normalize("30см", idx).normalized_text == "30 см"
    assert normalize("660х420х350 мм", idx).normalized_text == "660x420x350 мм"
