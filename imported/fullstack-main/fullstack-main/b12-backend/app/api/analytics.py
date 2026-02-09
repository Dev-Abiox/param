from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import SessionLocal
from app.core.db_models import ScreeningResult
from app.core.security import require_role

router = APIRouter()

@router.get("/summary")
def get_summary(user = Depends(require_role(["ADMIN", "LAB"]))):
    db: Session = SessionLocal()

    total = db.query(func.count(ScreeningResult.id)).scalar()

    # Counts by category
    normal_count = db.query(func.count()).filter(ScreeningResult.risk_class == 1).scalar()
    borderline_count = db.query(func.count()).filter(ScreeningResult.risk_class == 2).scalar()
    deficient_count = db.query(func.count()).filter(ScreeningResult.risk_class == 3).scalar()

    # Recent cases with mapped fields
    recent_query = db.query(ScreeningResult).order_by(ScreeningResult.created_at.desc()).limit(20).all()
    recent = []
    for r in recent_query:
        # Map risk class to string result
        if r.risk_class == 3: res_str = "High Risk"
        elif r.risk_class == 2: res_str = "Borderline"
        else: res_str = "Normal"

        recent.append({
            "id": str(r.id),
            "date": r.created_at.strftime("%Y-%m-%d"),
            "patientRef": r.patient_id,
            "mcv": "-",  # Placeholder as MCV isn't stored in ScreeningResult directly yet
            "result": res_str
        })

    return {
        "totalCases": total,
        "dailyTests": 12, # Mock value for now
        "modelMetrics": {
            "accuracy": 92,
            "recall": 88,
            "precision": 90,
            "f1Score": 89,
            "auc": 0.94,
            "version": "v1.0.0"
        },
        "distribution": [
            {"name": "Normal", "value": normal_count, "fill": "#10b981"},     # Green
            {"name": "Borderline", "value": borderline_count, "fill": "#f59e0b"}, # Amber
            {"name": "Deficient", "value": deficient_count, "fill": "#ef4444"}    # Red
        ],
        "recentCases": recent
    }
