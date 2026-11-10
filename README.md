# BrandPilot – The Phantoms

**AI-Powered Brand Governance Platform**

BrandPilot is an intelligent brand-governance platform that helps organisations maintain brand consistency and trust by reviewing content before publication. It identifies violations, explains findings, suggests corrections, and supports human approval workflows.

## 🚀 Live Project

- **Live Website:** https://brandpilot-frontend.vercel.app/
- **Backend API:** https://brandpilot-thephantoms.onrender.com
- **API Documentation:** https://brandpilot-thephantoms.onrender.com/docs
- **GitHub Repository:** https://github.com/rajatmanro-tech/BrandPilot-ThePhantoms

## 🎯 Problem Statement

Organisations publish content through multiple employees, agencies, and AI tools. Maintaining consistent brand identity across all these channels is difficult.

Incorrect claims, outdated information, inconsistent terminology, and off-brand visuals can damage brand credibility.

BrandPilot addresses this challenge by checking content against approved brand guidelines before publication.

## ✨ Key Features

- **Brand Management:** Create and manage brand profiles and guidelines.
- **Rule Management:** Define brand rules, categories, severity levels, and descriptions.
- **AI-Powered Text Review:** Analyse content and identify potential brand violations.
- **Explainable Findings:** Display detected issues with explanations and suggested corrections.
- **Image Review:** Check colour palette consistency and accessibility requirements.
- **Review Workflow:** Accept suggested corrections or override findings.
- **Approval Workflow:** Support human review and approval decisions.
- **Audit Logs:** Maintain records of review decisions and actions.

## 🛠️ Technology Stack

| Component | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Database Migrations | Alembic |
| Authentication | JWT |
| AI Integration | Groq, Google Gemini, OpenAI |
| Frontend Hosting | Vercel |
| Backend Hosting | Render |

## 🏗️ Architecture

BrandPilot follows a frontend-backend architecture.

1. Users interact with the frontend through the web application.
2. The frontend communicates with the FastAPI backend through REST APIs.
3. The backend processes requests, manages authentication, and performs brand reviews.
4. AI services assist with text analysis and review findings.
5. PostgreSQL stores application data, including users, brands, rules, reviews, and audit records.
6. Review decisions are recorded to support accountability and traceability.

## ⚙️ Local Setup

### Prerequisites

- Python 3.12 or compatible version
- PostgreSQL
- Git

### 1. Clone the repository

```bash
git clone https://github.com/rajatmanro-tech/BrandPilot-ThePhantoms.git
cd BrandPilot-ThePhantoms
```

### 2. Set up the backend

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment on Windows:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file inside the `backend` directory.

Configure the following variables:

```env
DATABASE_URL=your_postgresql_database_url
SECRET_KEY=your_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=openai/gpt-oss-20b
GEMINI_API_KEY=your_gemini_api_key
OPENAI_API_KEY=your_openai_api_key
```

Use your own credentials. Never commit API keys or database passwords to GitHub.

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the backend

```bash
uvicorn app.main:app --reload
```

Backend runs at:

`http://127.0.0.1:8000`

API documentation:

`http://127.0.0.1:8000/docs`

### 6. Run the frontend

Open `frontend/index.html` in a browser.

For local development, ensure the frontend API base URL points to your local backend.

## 🔐 Security

- JWT-based authentication.
- Environment-based configuration for sensitive credentials.
- Password hashing.
- Backend API validation.
- Human-controlled review and approval decisions.

## ⚠️ Current Limitations

- Image review currently focuses on deterministic colour-palette and accessibility checks rather than general-purpose image understanding.
- AI-generated findings may require human verification.
- Advanced document ingestion, expanded analytics, and external-contributor workflows are planned improvements.

## 👥 Team – The Phantoms

| Member | Role |
|---|---|
| Aditya Singh | Lead AI & RAG Engineer |
| Karanveer Singh | Multi-Modal & Computer Vision Developer |
| Rajat Manro | Backend & Systems Architect |
| Ranvir Singh | Frontend & Interactive UI Engineer |

## 🔮 Future Scope

- DOCX/PDF document ingestion with approved exports.
- Insights dashboard and guideline-ambiguity detection.
- External-contributor agency workflow with scoped access.
- Improved accessibility and reliability testing.

## 📄 License

This project was developed as part of CodeTitans India 2026 by Team The Phantoms.