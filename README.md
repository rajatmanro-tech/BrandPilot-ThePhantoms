# BrandPilot – The Phantoms

**AI-Assisted Brand Governance Platform**

BrandPilot helps teams review marketing and other brand-facing content before publication. It brings brand workspaces, guideline rules, text and visual checks, document review, review decisions, contributor access, and governance information into one web application.

## Live Project

| Resource | Link |
|---|---|
| Live application | https://brandpilot-frontend.vercel.app/ |
| Backend API | https://brandpilot-thephantoms.onrender.com |
| API documentation | https://brandpilot-thephantoms.onrender.com/docs |
| Source code | https://github.com/rajatmanro-tech/BrandPilot-ThePhantoms |

## Product Screenshots

The screenshots below show the application's main sections.

### Brand setup
![Brand setup](docs/screenshots/01-brand-setup.png)

### Text review
![Text review](docs/screenshots/02-text-review.png)

### Image review
![Image review](docs/screenshots/03-image-review.png)

### Contributor access
![Contributors](docs/screenshots/04-contributors.png)

### External content submission
![External submission](docs/screenshots/05-external-submit.png)

### Document review interface
![Document review](docs/screenshots/06-document-review.png)

### Governance dashboard
![Governance dashboard](docs/screenshots/07-governance-dashboard.png)

### Account
![Account](docs/screenshots/08-account.png)

## Problem

Organisations publish content through employees, agencies, and AI tools. As the number of contributors grows, it becomes harder to keep language, claims, visual identity, and approval practices consistent. BrandPilot helps teams check content against their brand rules before publication, understand potential issues, and retain a record of review decisions.

## Features

- **Brand workspaces:** Create and switch between brand workspaces.
- **Brand rules:** Define requirements by category, title, optional rule code, and supporting details.
- **Text review:** Submit copy for a pre-flight review and inspect flagged phrases, explanations, and suggested fixes.
- **Review decisions:** Accept suggested replacements or record overrides with reasons, where supported by the review workflow.
- **Image review:** Run deterministic checks using supplied brand colours and accessibility settings. This is not general-purpose image recognition.
- **Contributor access:** Create brand-scoped contributor tokens with an expiry and manage token history.
- **External submission:** Allow a contributor to submit content using an issued token.
- **Document review:** Upload text-based PDF and DOCX files, extract their text, run AI-assisted review, inspect findings, record per-finding decisions, approve the review, and export the approved document as a PDF. The deployed upload-to-approved-export workflow has been tested.
- **Governance dashboard:** View review metrics and potentially confusing guidelines. Analytics are most meaningful when review history is populated.
- **Audit trail:** Record relevant review actions and decisions to support traceability.

## Document Review Workflow

1. Upload a PDF or DOCX file from the Documents section.
2. BrandPilot extracts the document text and runs the review.
3. Inspect the findings, their severity, original text, and suggested corrections.
4. Accept an appropriate suggested fix or record an override with a reason.
5. Submit the decisions and complete the approval action when the content is ready.
6. Download the approved PDF export and verify its content and status.

Review suggestions should be checked by a human before approval. Unsupported claims must be backed by evidence, and conflicting offer dates or other factual details must be verified rather than guessed.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| ORM and migrations | SQLAlchemy, Alembic |
| Authentication | JWT |
| AI integrations | Groq, Google Gemini, OpenAI |
| Image processing | Pillow |
| Hosting | Vercel (frontend), Render (backend) |

## Architecture Overview

1. A user interacts with the web application.
2. The frontend sends requests to the FastAPI REST API.
3. The backend validates requests, applies authentication and access checks, and coordinates review workflows.
4. Review services use configured deterministic checks and AI integrations where applicable.
5. PostgreSQL stores application data such as users, workspaces, rules, reviews, contributor tokens, decisions, and audit records.
6. Review decisions and relevant actions are recorded to support traceability.

## Repository Structure

```text
BrandPilot-ThePhantoms/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── schemas/
│   │   └── services/
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
├── docs/
│   └── screenshots/
├── README.md
└── LICENSE
```

## Run Locally

### Prerequisites

- Python 3.12
- PostgreSQL
- Git

### 1. Clone the repository

```bash
git clone https://github.com/rajatmanro-tech/BrandPilot-ThePhantoms.git
cd BrandPilot-ThePhantoms
```

### 2. Create and activate a virtual environment

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the `backend` directory. Use `.env.example` as the reference and provide your own database URL, a strong secret key, and the API keys for the integrations you intend to use.

Typical configuration keys include:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/brandpilot_db
SECRET_KEY=replace-with-a-long-random-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-20b

FRONTEND_URL=http://127.0.0.1:3000
```

Only configure the providers you use. Never commit API keys, passwords, or production secrets.

### 5. Apply database migrations

From the `backend` directory:

```bash
alembic upgrade head
```

### 6. Start the backend

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000` and its interactive documentation at `http://127.0.0.1:8000/docs`.

### 7. Open the frontend

Open `frontend/index.html` in a browser. For local use, ensure the frontend API base URL is configured to point to the local backend.

## Testing

The repository contains backend tests. Run the applicable test suite from the backend environment:

```bash
pytest
```

For a deployment smoke test, verify the live frontend and API, then exercise the main workflows: authentication, brand setup, text review, image review, document upload and review, decision submission, approval, approved PDF download, contributor submission, and governance dashboard updates.

Report the exact automated tests executed, environment, results, and any known failures. Do not describe an automated test as passed unless it was actually run against the submitted version.

## Current Limitations and Validation Notes

- Image review uses deterministic checks based on supplied colour and accessibility values; it does not perform general-purpose visual understanding or logo recognition.
- AI-generated review findings can require human verification.
- Some deterministic pre-flight checks depend on explicitly configured rule codes and available brand data.
- Document review supports text-based PDF/DOCX files. Scanned or image-only PDFs require OCR, which is not currently configured.
- Governance analytics should be evaluated with populated review and decision history.
- External-contributor access should be tested for token expiry, revocation, invalid tokens, and brand scoping.

## Team – The Phantoms

| Member | Role |
|---|---|
| Aditya Singh | Lead AI & RAG Engineer |
| Karanveer Singh | Multimodal & Computer Vision Developer |
| Rajat Manro | Backend & Systems Architect |
| Ranvir Singh | Frontend & Interactive UI Engineer |

## Roadmap

- Add OCR support for scanned PDFs and strengthen document export formatting and approval evidence.
- Expand review analytics and guideline-ambiguity detection.
- Strengthen scoped and revocable access for external contributors.
- Improve automated integration, error-handling, and usability testing.
- Expand visual analysis while keeping its capabilities and limitations explicit.

## License

See [LICENSE](LICENSE). Developed for CodeTitans India 2026 by Team The Phantoms.
