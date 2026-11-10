# BrandPilot integrated backend

This package keeps the existing FastAPI/PostgreSQL backend and adds the teammate engines.

## Added capabilities

- `POST /brands/{brand_id}/preflight`: deterministic text checks using explicitly configured `rule_code` values.
- `POST /brands/{brand_id}/image-reviews`: deterministic visual/accessibility checks. The caller must supply the approved brand palette as JSON; the demo palette is not silently used.
- `GET /brands/{brand_id}/image-reviews`: image review history.
- `POST /reviews/{review_id}/decisions`: persist an accepted replacement or an override reason.
- `GET /reviews/{review_id}/decisions`: retrieve saved decisions.
- Audit log entries are created for preflight, image reviews and review decisions.

## Teammate modules

The uploaded modules are installed as:
- `app/services/text_ingest.py`
- `app/services/preflight.py`
- `app/services/visual_review.py`

The import in preflight was adjusted to the package path. The original algorithms were otherwise retained.

## Important limitations and configuration

1. The deterministic preflight engine implements these rule codes only: `X-003`, `X-007`, `T-031`, `T-044`, `V-002`, `A-003`. Add the relevant `rule_code` to a Brand Rule through the API. Arbitrary prose rules continue to be evaluated by the existing AI review path, not magically converted into deterministic checks.
2. `F-001` and `F-003` are intentionally not enabled because the current database has no per-brand approved founding-year field. The demo engine's hardcoded founding year must not be applied to other brands.
3. The image endpoint requires the approved palette to be sent in the request (`palette` form field as a JSON object). It does not assume the Aranya demo palette. Logo matching is skipped until an approved logo template is supplied through a future brand-assets endpoint. Findings without vision text regions are low-confidence questions where appropriate.
4. The visual engine is deterministic and does not use a vision model. Text-region detection is not available in this integration, so contrast analysis uses its documented whole-image heuristic.
5. Accepting a finding requires a `replacement_text`. Overrides require a reason. These decisions are stored and audit logged; they do not automatically mutate the original review content.
6. Image upload size is limited to 10 MB.

## Install and migrate (PowerShell)

Use the existing Python 3.12 virtual environment:

```powershell
cd D:\BrandPilot-ThePhantoms\backend\app\Hackathon\BrandPilot-ThePhantoms\backend
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/docs`.

## New endpoints

All endpoints require a bearer token. Image reviews use `multipart/form-data`.
