from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.engine import B12ClinicalEngine
from app.core.models import ScreeningRequest, ScreeningResponse
from app.core.security import require_role
from app.core.database import SessionLocal
from app.core.db_models import Patient, ScreeningResult, AuditLog

router = APIRouter()
engine = B12ClinicalEngine()

@router.post("/predict", response_model=ScreeningResponse)
def predict_b12(
    data: ScreeningRequest,
    user = Depends(require_role(["LAB", "DOCTOR", "ADMIN"]))
):
    db: Session = SessionLocal()

    # Ensure patient exists
    patient = db.query(Patient).filter(Patient.id == data.patientId).first()
    if not patient:
        patient = Patient(id=data.patientId, age=data.cbc.Age, sex=data.cbc.Sex)
        db.add(patient)

    # Run engine
    result = engine.predict(data.cbc.dict())

    # Save screening
    screening = ScreeningResult(
        patient_id=data.patientId,
        user_id=user.username,
        risk_class=result["riskClass"],
        label=result["label"],
        probabilities=result["probabilities"],
        rules_fired=result["rulesFired"],
        model_version=result["modelVersion"]
    )
    db.add(screening)

    # Audit
    audit = AuditLog(
        user_id=user.username,
        action="SCREEN_B12",
        entity="CBC",
        details={"patient": data.patientId, "risk": result["riskClass"]}
    )
    
    db.add(audit)

    db.commit()

    return {
        "riskClass": result["riskClass"],
        "label": result["label"],
        "probabilities": result["probabilities"],
        "rulesFired": result["rulesFired"],
        "recommendation": "Confirm with Serum B12 ± MMA as clinically indicated",
        "modelVersion": result["modelVersion"],
        "indices": result.get("indices", {})
    }
