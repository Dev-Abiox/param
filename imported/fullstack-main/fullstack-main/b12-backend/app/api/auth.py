from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.security import create_access_token

router = APIRouter()

# Temporary in-memory users (replace with DB later)
USERS = {
    "admin": {"password": "admin", "role": "ADMIN", "name": "System Administrator"},
    "lab": {"password": "lab", "role": "LAB", "name": "City Pathology Labs"},
    "doctor": {"password": "doctor", "role": "DOCTOR", "name": "Dr. Sharma"}
}

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    id: str
    name: str
    role: str
    access_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest):
    user = USERS.get(data.username)
    if not user or user["password"] != data.password:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": data.username,
        "role": user["role"]
    })

    return {
        "id": data.username,
        "name": user["name"],
        "role": user["role"],
        "access_token": token,
        "token_type": "bearer"
    }
