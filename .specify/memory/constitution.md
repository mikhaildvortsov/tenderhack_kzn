<!--
Sync Impact Report
Version change: (template) → 1.0.0
Modified principles: n/a (initial ratification)
Added sections: Core Principles I–VI, Technical Constraints, Development Workflow, Governance
Removed sections: none
Follow-up TODOs: none
-->
# Tender Hack KTRU Autofill Constitution

## Core Principles

### I. KTRU Is the Source of Truth
The KTRU reference (actual positions only: `nsiKTRUNew_all-actual_*.xml`) MUST be the
authoritative source for characteristics, allowed values, ranges and units. Sample xlsx exports
are auxiliary (synonyms, frequencies, test cases) and MUST NOT override KTRU. Positions from
`not-actual` files MUST NOT be suggested or matched.

### II. Open and Lightweight Models Only
Only open ML models are allowed; total inference VRAM MUST NOT exceed 40 GB, and the design
SHOULD target well below it. Proprietary LLM APIs (OpenAI, Gemini, Claude, etc.) and paid search
APIs (Yandex Search, Google Custom Search) MUST NOT be used. Heavy models MUST be justified by
measured quality gain over a lighter baseline.

### III. Explainable Decisions
Every extracted characteristic, unification, correction and KTRU narrowing step MUST carry a
human-readable rationale and confidence. Silent value substitution is forbidden; low-confidence
changes MUST require user confirmation.

### IV. Test on Real and Broken Data (NON-NEGOTIABLE)
Features MUST be verified against real cases from the provided exports and against deliberately
broken input: typos, wrong units, out-of-range values, missing and contradictory characteristics,
ambiguous KTRU. Evaluation metrics (KTRU accuracy, extraction F1, error detection P/R, latency)
MUST be reproducible by one command.

### V. Stateless and Scalable by Design
API services MUST be stateless and horizontally scalable; the KTRU index and data stores are
separate components; ETL MUST be idempotent. The whole system MUST start with a single
command on Linux and provide a web interface.

### VI. Simplicity and Plain Code
No low-code/no-code platforms. Prefer deterministic rules, fuzzy matching and classical
retrieval before ML; add model complexity only where measurement shows it is needed (YAGNI).

## Technical Constraints

- Target OS: Linux; delivery: web UI + documented REST API (OpenAPI).
- Scope categories: clothing, furniture, tools.
- Offline operation: no runtime dependency on external paid or proprietary services.
- Required deliverables: working demo, repository, BPMN 2.0 process diagram, presentation.

## Development Workflow

- Spec-Kit flow: constitution → specify → plan → tasks → implement → converge.
- Tests precede merging; failing tests MUST NOT be removed without approval.
- Secrets MUST NOT be committed; dependencies and model additions require a recorded rationale.
- Changes to the KTRU data model or ETL require a migration/re-index note.

## Governance

This constitution supersedes other practices. Amendments require a written change, rationale
and version bump (MAJOR: principle removal/redefinition; MINOR: new principle or material
expansion; PATCH: wording). Plans and reviews MUST verify compliance with these principles;
deviations MUST be documented with justification in the plan's complexity section.

**Version**: 1.0.0 | **Ratified**: 2026-10-10 | **Last Amended**: 2026-10-10
