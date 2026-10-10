import pytest

from app.schemas import AnalyzeRequest, AnalyzeResponse, NarrowingStep, Override
from engine.pipeline import analyze, analyze_steps
from tests.fixtures.mini_index import build_mini_index


@pytest.fixture(scope="module")
def idx():
    return build_mini_index()


def run(idx, text, **kw):
    return analyze(AnalyzeRequest(text=text, **kw), idx)


def chars(r):
    return {c.name: c for c in r.characteristics}


def types(r):
    return {i.type for i in r.issues}


def test_full_hammer_query(idx):
    text = "молоток слесарный 500 г, длина рукоятки 300 мм"
    r = run(idx, text)
    assert r.category.id == "tools" and r.status == "resolved"
    assert r.final.code == "25.73.30.141-00000001"
    m = chars(r)["Масса молотка"]
    assert m.value == "0.5" and m.unit == "Килограмм" and m.status == "corrected"
    assert m.span.text == "500 г" and text[m.span.start:m.span.end] == "500 г"
    assert "0.4–0.6 кг" in m.reason
    assert chars(r)["Длина рукоятки"].value == "300"
    assert [s.stage for s in r.narrowing][:2] == ["category", "name"]
    assert all(s.before >= s.after for s in r.narrowing)
    assert "total" in r.timings_ms


def test_typo(idx):
    r = run(idx, "молатак 500г")
    (t,) = [i for i in r.issues if i.type == "typo"]
    assert t.auto_applied and t.suggestion.replacement == "молоток"
    assert r.category.id == "tools" and r.candidates


def test_layout(idx):
    r = run(idx, "vjkjnjr")
    assert "layout" in types(r) and r.candidates[0].name == "Молоток"


def test_unit_mismatch(idx):
    r = run(idx, "молоток длина рукоятки 5 кг")
    (i,) = [i for i in r.issues if i.type == "unit_mismatch"]
    assert i.span.text == "5 кг" and i.severity == "error"
    assert chars(r)["Длина рукоятки"].status == "error"


def test_ambiguous_table_has_recommendation(idx):
    r = run(idx, "стол")
    assert r.status == "ambiguous" and r.category.id == "furniture"
    assert r.recommendations and r.recommendations[0].options
    assert any(x.kind == "clarify" for x in r.recommendations)


def test_empty(idx):
    for text in ("", "   ", "ывапролдж"):
        r = run(idx, text)
        assert r.status == "empty" and r.recommendations


def test_out_of_range(idx):
    r = run(idx, "молоток масса 15 кг")
    (i,) = [i for i in r.issues if i.type == "out_of_range"]
    assert "15 кг" in i.message and "2.5" in i.reason
    assert r.candidates  # value does not wipe out candidates


def test_category_mismatch(idx):
    r = run(idx, "автомобиль")
    assert r.status == "not_found" and "category_mismatch" in types(r)
    assert any(x.kind == "fix" for x in r.recommendations)


def test_selected_code(idx):
    r = run(idx, "молоток", selected_code="25.73.30.141-00000003")
    assert r.status == "resolved" and r.final.code == "25.73.30.141-00000003"


def test_ignored_issues(idx):
    r = run(idx, "молоток длина рукоятки 5 кг", ignored_issues=["unit_mismatch:5 кг"])
    assert "unit_mismatch" not in types(r)
    r = run(idx, "молатак", ignored_issues=["typo:молатак"])
    assert "typo" not in types(r)


def test_override(idx):
    r = run(idx, "молоток", overrides=[Override(name="Масса молотка", value="1500", unit="г")])
    m = chars(r)["Масса молотка"]
    assert m.value == "1.5" and m.unit == "Килограмм"
    assert all(c.name == "Молоток" for c in r.candidates) and r.candidates_total == 1


def test_qualitative_and_dims(idx):
    r = run(idx, "стол офисный 1200х600х750 мм ЛДСП")
    c = chars(r)
    assert c["Длина"].value == "1200" and c["Ширина"].value == "600" and c["Высота"].value == "750"
    assert c["Материал столешницы"].value == "ЛДСП"
    assert r.final and r.final.name == "Стол офисный"


def test_yes_no_and_size(idx):
    r = run(idx, "кресло офисное без подлокотников")
    assert chars(r)["Наличие подлокотников"].value == "Нет"
    r = run(idx, "куртка мужская зимняя размер 52")
    assert chars(r)["Российский размер"].value == "52" and chars(r)["Сезон"].value == "Зимний"


def test_contradiction_and_unknown(idx):
    r = run(idx, "молоток масса 1 кг масса 2 кг")
    assert "contradiction" in types(r)
    r = run(idx, "куртка мужская 220 вт")
    assert "unknown_characteristic" in types(r)


def test_steps_stream(idx):
    items = list(analyze_steps(AnalyzeRequest(text="молоток слесарный 500 г"), idx))
    assert isinstance(items[-1], AnalyzeResponse)
    assert all(isinstance(x, NarrowingStep) for x in items[:-1]) and len(items) >= 3
    assert [s.step for s in items[-1].narrowing] == list(range(1, len(items[-1].narrowing) + 1))


def test_issue_ids_stable(idx):
    r = run(idx, "молоток длина рукоятки 5 кг")
    assert all(i.id.startswith(i.type + ":") for i in r.issues)
