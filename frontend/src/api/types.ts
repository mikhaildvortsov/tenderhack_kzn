// 1:1 с specs/001-ktru-autofill/contracts/api.md
export type Status = 'resolved' | 'ambiguous' | 'not_found' | 'empty';
export interface Span { start: number; end: number; text: string }
export interface CategoryGuess { id: 'clothing' | 'furniture' | 'tools' | 'unknown'; name: string; confidence: number }
export interface Candidate {
  code: string; name: string; okpd2_code: string; okpd2_name: string;
  unit: string | null; score: number; matched_chars: number; total_chars: number;
}
export type CharStatus = 'ok' | 'corrected' | 'error' | 'missing' | 'suggested';
export interface ExtractedCharacteristic {
  id: string; name: string;
  raw_value: string | null; raw_unit: string | null;
  value: string | null; unit: string | null;
  value_kind: 'quantitative' | 'qualitative';
  span: Span | null;
  status: CharStatus;
  confidence: number;
  reason: string;
  required: boolean;
  allowed_values: string[];
}
export type IssueType = 'typo' | 'layout' | 'unit_mismatch' | 'value_not_allowed' | 'out_of_range'
  | 'missing_required' | 'contradiction' | 'unknown_characteristic' | 'category_mismatch';
export interface Issue {
  id: string; type: IssueType; severity: 'error' | 'warning' | 'info';
  span: Span | null; message: string; reason: string;
  suggestion: { replacement: string; label: string } | null;
  auto_applied: boolean;
}
export interface NarrowingStep {
  step: number; stage: 'category' | 'name' | 'characteristic' | 'ranking';
  label: string; characteristic: string | null; value: string | null;
  before: number; after: number; excluded_sample: string[];
}
export interface Recommendation {
  id: string; kind: 'add' | 'clarify' | 'fix';
  characteristic: string | null; message: string; options: string[];
  expected_remaining: number | null;
}
export interface AnalyzeResponse {
  status: Status; text: string; normalized_text: string;
  category: CategoryGuess; final: Candidate | null;
  candidates: Candidate[]; candidates_total: number;
  characteristics: ExtractedCharacteristic[]; issues: Issue[];
  narrowing: NarrowingStep[]; recommendations: Recommendation[];
  timings_ms: Record<string, number>;
}
export interface Override { name: string; value: string; unit?: string | null }
export interface AnalyzeRequest {
  text: string;
  overrides?: Override[];
  ignored_issues?: string[];
  selected_code?: string | null;
}
export interface KtruValue { text?: string; min?: number; min_op?: string; max?: number; max_op?: string; value?: number; unit?: string | null; display: string }
export interface KtruCharacteristic { code: string | null; name: string; type: 1 | 2; kind: number | null; required: boolean; values: KtruValue[] }
export interface KtruPosition { code: string; name: string; okpd2_code: string; okpd2_name: string; category: string; unit: string | null; status: string; characteristics: KtruCharacteristic[] }
export interface Example { category: string; text: string; note: string }
