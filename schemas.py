from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    inspector_id: str = Field(min_length=2, max_length=80)
    official_email: EmailStr
    department_zone: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=8, max_length=128)
    designation: str = Field(min_length=2, max_length=120)


class LoginRequest(BaseModel):
    official_email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class InspectorResponse(BaseModel):
    inspector_id: str
    official_email: EmailStr
    department_zone: str
    designation: str
    role: str


class AuditSummary(BaseModel):
    id: int
    brand_name: str
    batch_number: str
    compliance_status: str
    compliance_score: int
    created_at: datetime
