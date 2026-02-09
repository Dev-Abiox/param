from fastapi import FastAPI
from app.api import screening, auth, analytics
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Clinomic B12 Screening Platform",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Authentication & RBAC
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])

# Core Clinical Screening Engine
app.include_router(screening.router, prefix="/api/screening", tags=["B12 Screening"])

# Admin / Lab Analytics
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])

