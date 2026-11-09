# BrandPilot - Text Ingest and Pre-flight Engine (AI/RAG lane)

Owner: Aditya Singh, Lead AI and RAG Engineer, team The Phantoms.

This is the text path of the pre-flight engine described in the Round 1 plan (sections 4 and 6).
It reads text input, reviews it against the brand kit with deterministic checks, and returns
explainable, source-cited findings with a risk score and approval routing.

## Files

| File | Purpose |
|---|---|
| `text_ingest.py` | Step 1, Ingest and parse. Pasted text, bytes, `.txt`, `.md` become clean canonical text plus paragraph and sentence segments with exact character offsets, a SHA-256 hash, and prompt-injection flags. |
| `preflight.py` | Steps 2-4. Five deterministic reviewers, aggregator, risk score, role routing, report formatter, CLI. |
| `test_preflight.py` | 31 tests, including the seeded violations from Appendix B.3. |

No third-party dependencies. Python 3.9 or newer.

## Usage

```bash
python preflight.py caption.txt                 # readable report
python preflight.py caption.txt --json          # full JSON report
echo "Our #1 night cream since 2019" | python preflight.py --channel social
python -m unittest -v test_preflight            # run the tests
```

From code:

```python
from preflight import run_preflight

report = run_preflight("Clinically proven to erase acne in 7 days!", channel="social")
report.risk_level     # "CRITICAL"
report.routing        # ["brand_manager", "legal"]
for f in report.findings:
    print(f.rule_id, f.severity, f.quote, f.span_start, f.span_end, f.suggestion)
```

## What the five reviewers check (all deterministic, no external calls)

| Reviewer | Rules | What it catches |
|---|---|---|
| claims | X-003, X-007 | Cure/treat/erase/destroy wording near a skin condition; "clinically proven" without a trial ID; "100% safe", "guaranteed results", "100% natural/chemical-free" |
| terminology | T-031, T-044 | "best-in-class", "world-class", unqualified "#1"; "gurus", "experts-for-hire"; "users" outside product docs |
| facts | F-001, F-003 | "Since 2019" and founding years that conflict with the approved 2016 |
| tone | V-002 | Sentences over 22 words; fear or pressure urgency (requires a typed reason to waive) |
| readability | A-003 | Flesch-Kincaid grade above 8 (English text of 40+ words) |

## Guarantees built into the engine

- **No source, no finding.** Every finding carries a rule ID and source clause. Hits without a known rule are dropped and listed in `report.dropped_hits`.
- **Exact offsets.** `text[span_start:span_end] == quote` for every span finding, so editor highlights line up.
- **Never silently skips a check.** If a reviewer crashes, the report is marked `complete=False` and risk is `UNKNOWN`, never `NONE`.
- **Humans decide.** Brand manager sign-off is always required. Legal is added for any HIGH or CRITICAL claim finding. Nothing is approved or published here.
- **Untrusted input.** Pasted text is treated as data. Injection-style phrases set `quarantined=True` and force manual review.
- **Deterministic.** The same input always yields the same findings and finding IDs.
- **Honest disclosure.** Every report states that this pass used no AI model.

## Known limitations (stated honestly)

- This is the deterministic layer only. The LLM claim extractor, NLI substantiation, and LLM tone judge from plan section 6.3 are the next layer and are not in this package.
- The brand kit is hard-coded to the demo brand (Aranya Botanics, Appendix B). Brand Brain ingestion will build a `BrandKit` from uploaded guidelines.
- Rule patterns are written for English. Hindi text is ingested and segmented correctly, but the reviewers do not yet check Hindi wording.
- "Unqualified superlatives" beyond T-031's explicit list (for example "India's most trusted") are not caught here; they belong to the LLM claims reviewer.
- The `100% natural/chemical-free` pattern is filed under X-007 (absolute claims) as our interpretation of Appendix B.3; it has no separate clause ID in the kit.
- Sentence splitting is rule-based, so abbreviations such as "Dr." can cause an extra split.
- Image and DOCX/PDF inputs are out of scope for this package.
