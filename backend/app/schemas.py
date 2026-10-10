"""API contract v1 (mirrors specs/001-ktru-autofill/contracts/api.md and frontend/src/api/types.ts)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Status = Literal["resolved", "ambiguous", "not_found", "empty"]
IssueType = Literal[
    "typo", "layout", "unit_mismatch", "value_not_allowed", "out_of_range",
    "missing_required", "contradiction", "unknown_characteristic", "category_mismatch",
]


class Override(BaseModel):
    name: str
    value: str
    unit: Optional[str] = None


class AnalyzeRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    overrides: list[Override] = Field(default_factory=list)
    ignored_issues: list[str] = Field(default_factory=list)
    selected_code: Optional[str] = None


class Span(BaseModel):
    start: int
    end: int
    text: str


class CategoryGuess(BaseModel):
    id: Literal["clothing", "furniture", "tools", "unknown"]
    name: str
    confidence: float


class Candidate(BaseModel):
    code: str
    name: str
    okpd2_code: str
    okpd2_name: str
    unit: Optional[str] = None
    score: float
    matched_chars: int
    total_chars: int


class ExtractedCharacteristic(BaseModel):
    id: str
    name: str
    raw_value: Optional[str] = None
    raw_unit: Optional[str] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    value_kind: Literal["quantitative", "qualitative"]
    span: Optional[Span] = None
    status: Literal["ok", "corrected", "error", "missing", "suggested"]
    confidence: float
    reason: str
    required: bool = False
    allowed_values: list[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    replacement: str
    label: str


class Issue(BaseModel):
    id: str
    type: IssueType
    severity: Literal["error", "warning", "info"]
    span: Optional[Span] = None
    message: str
    reason: str
    suggestion: Optional[Suggestion] = None
    auto_applied: bool = False


class NarrowingStep(BaseModel):
    step: int
    stage: Literal["category", "name", "characteristic", "ranking"]
    label: str
    characteristic: Optional[str] = None
    value: Optional[str] = None
    before: int
    after: int
    excluded_sample: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    id: str
    kind: Literal["add", "clarify", "fix"]
    characteristic: Optional[str] = None
    message: str
    options: list[str] = Field(default_factory=list)
    expected_remaining: Optional[int] = None


class AnalyzeResponse(BaseModel):
    status: Status
    text: str
    normalized_text: str
    category: CategoryGuess
    final: Optional[Candidate] = None
    candidates: list[Candidate] = Field(default_factory=list)
    candidates_total: int = 0
    characteristics: list[ExtractedCharacteristic] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    narrowing: list[NarrowingStep] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class KtruValue(BaseModel):
    text: Optional[str] = None
    min: Optional[float] = None
    min_op: Optional[str] = None
    max: Optional[float] = None
    max_op: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    display: str


class KtruCharacteristic(BaseModel):
    code: Optional[str] = None
    name: str
    type: int
    kind: Optional[int] = None
    required: bool
    values: list[KtruValue] = Field(default_factory=list)


class KtruPosition(BaseModel):
    code: str
    name: str
    okpd2_code: str
    okpd2_name: str
    category: str
    unit: Optional[str] = None
    status: str = "ACTIVE"
    characteristics: list[KtruCharacteristic] = Field(default_factory=list)


class Example(BaseModel):
    category: str
    text: str
    note: str


class Health(BaseModel):
    status: str
    positions: int
    index_loaded: bool
    version: str
