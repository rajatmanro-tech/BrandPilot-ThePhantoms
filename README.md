# BrandPilot – The Phantoms

**AI-powered Brand Governance and Content Review Platform**

BrandPilot helps organisations maintain a consistent and trustworthy brand identity by reviewing text and visual content against approved brand guidelines before publication.

## Features

- **Brand Management:** Create and manage brand workspaces.
- **Custom Brand Rules:** Define organisation-specific content guidelines.
- **AI-Powered Text Review:** Detect tone, terminology and potentially unsupported claims.
- **Visual Review:** Identify off-palette colours and accessibility issues.
- **Human Approval Workflow:** Accept suggested fixes or override findings with a reason.
- **Audit Trail:** Record review decisions and verify audit-chain integrity.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| AI integrations | Groq, Gemini, OpenAI |

## Project Structure

```text
BrandPilot-ThePhantoms/
├── frontend/
│   └── index.html
├── backend/
│   ├── app/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── routes/
│   │   ├── schemas/
│   │   └── services/
│   ├── migrations/
│   ├── tests/
│   ├── .env.example
│   ├── alembic.ini
│   └── requirements.txt
├── docs/
├── .gitignore
├── LICENSE
└── README.md
```

## Prerequisites

- Python 3.12
- PostgreSQL
- Git

## Backend Setup

Clone the repository:

```bash
git clone https://github.com/rajatmanro-tech/BrandPilot-ThePhantoms.git
cd BrandPilot-ThePhantoms
```

Create and activate a virtual environment:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure environment variables:

```powershell
Copy-Item .env.example .env
```

Update `.env` with your PostgreSQL connection string and required AI provider credentials.

Create the database in PostgreSQL, then run:

```bash
alembic upgrade head
```

Start the backend:

```bash
uvicorn app.main:app --reload
```

Backend: http://127.0.0.1:8000

API documentation: http://127.0.0.1:8000/docs

## Frontend Setup

Open a second terminal from the repository root:

```powershell
cd frontend
py -m http.server 3000
```

Open http://127.0.0.1:3000

The frontend connects to the local backend at `http://127.0.0.1:8000`.

## Security

- Never commit `.env` files or API keys.
- Use `.env.example` as the configuration template.
- Keep virtual environments and Python cache files out of version control.

## Current Limitations

- Visual review currently uses deterministic palette and accessibility checks rather than general-purpose image understanding.
- Aggregate dashboard analytics are not currently exposed by the backend API.
- AI review availability depends on the configured provider and its API limits.

## Team

**The Phantoms**

Built for CodeTitans India 2026.