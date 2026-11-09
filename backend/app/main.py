
from fastapi import FastAPI, HTTPException
from app.db.database import check_database_connection
from app.routes.auth import router as auth_router
from app.routes.brands import router as brands_router
from app.routes.rules import router as rules_router
from app.routes.reviews import router as reviews_router
from fastapi.middleware.cors import CORSMiddleware
from app.routes.audit_logs import router as audit_logs_router
app = FastAPI(
    title="BrandPilot API",
    description="AI-powered Brand Governance Platform",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(brands_router)
app.include_router(rules_router)
app.include_router(reviews_router)
app.include_router(audit_logs_router)
@app.get("/")
def root():
    return {
        "message": "Welcome to BrandPilot API",
        "status": "running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "backend"
    }
@app.get("/db-health")
def database_health():
    try:
        check_database_connection()
        return {
            "status": "connected",
            "database": "brandpilot_db"
        }
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failed: {str(error)}"
        )
