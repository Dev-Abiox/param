from sqlalchemy import Column, Integer, String, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    name = Column(String)
    role = Column(String)

class Patient(Base):
    __tablename__ = "patients"
    id = Column(String, primary_key=True)
    age = Column(Integer)
    sex = Column(String)

class ScreeningResult(Base):
    __tablename__ = "screenings"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, ForeignKey("patients.id"))
    user_id = Column(String, ForeignKey("users.id"))
    risk_class = Column(Integer)
    label = Column(String)
    probabilities = Column(JSON)
    rules_fired = Column(JSON)
    model_version = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String)
    action = Column(String)
    entity = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    details = Column(JSON)
