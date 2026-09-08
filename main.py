from __future__ import annotations

import json
import os
import re
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image
from sqlalchemy.orm import Session

from .auth import (
    create_access_token,
    get_current_inspector,
    hash_password,
    require_senior_officer,
    verify_password,
)
from .database import Base, engine, get_db
from .models import Audit, Inspector
from .ocr_engine import assess_image_quality, extract_text
from .report_engine import build_csv, build_pdf
from .schemas import (
    AuditSummary,
    InspectorResponse,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from .validator import audit_package


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Legal Metrology Compliance Scanner",
    version="1.0.0",
    description="SIH 26034 inspection-assistance API",
)

origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.getenv("UPLOAD_MAX_MB", "10")) * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "legal-metrology-compliance-scanner"}


@app.post("/api/v1/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(Inspector).filter(Inspector.official_email == payload.official_email).first():
        raise HTTPException(409, "Official email already registered")
    if db.query(Inspector).filter(Inspector.inspector_id == payload.inspector_id).first():
        raise HTTPException(409, "Inspector ID already registered")

    role = "senior_officer" if payload.designation.strip().lower() == "senior officer" else "inspector"
    inspector = Inspector(
        inspector_id=payload.inspector_id.strip(),
        official_email=payload.official_email.lower(),
        department_zone=payload.department_zone.strip(),
        designation=payload.designation.strip(),
        role=role,
        password_hash=hash_password(payload.password),
    )
    db.add(inspector)
    db.commit()
    return TokenResponse(access_token=create_access_token(inspector.official_email))


@app.post("/api/v1/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    inspector = db.query(Inspector).filter(Inspector.official_email == payload.official_email.lower()).first()
    if not inspector or not verify_password(payload.password, inspector.password_hash):
        raise HTTPException(status_code=401, detail="Invalid official email or password")
    return TokenResponse(access_token=create_access_token(inspector.official_email))


@app.get("/api/v1/auth/me", response_model=InspectorResponse)
def me(inspector: Inspector = Depends(get_current_inspector)):
    return InspectorResponse(
        inspector_id=inspector.inspector_id,
        official_email=inspector.official_email,
        department_zone=inspector.department_zone,
        designation=inspector.designation,
        role=inspector.role,
    )


@app.post("/api/v1/analyze-package")
async def analyze_package(
    image: UploadFile = File(...),
    pdp_area_cm2: float = Form(..., gt=0),
    package_height_mm: float = Form(..., gt=0),
    brand_name: str = Form("Unknown"),
    batch_number: str = Form("Not detected"),
    inspector: Inspector = Depends(get_current_inspector),
    db: Session = Depends(get_db),
):
    if image.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Only JPEG, PNG and WebP images are accepted")

    data = await image.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")

    decoded = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise HTTPException(400, "Could not decode image")

    quality = assess_image_quality(decoded)
    ocr_rows, quality = extract_text(decoded, package_height_mm)
    validation = audit_package(pdp_area_cm2, ocr_rows)

    # Best-effort metadata extraction.
    combined = " ".join(row["text"] for row in ocr_rows)
    mrp_match = re.search(r"(?:MRP|Maximum Retail Price)\s*[:\-]?\s*(?:₹|Rs\.?)?\s*([0-9]+(?:\.[0-9]+)?)", combined, re.I)
    brand = brand_name.strip() if brand_name.strip() != "Unknown" else (ocr_rows[0]["text"] if ocr_rows else "Unknown")

    result = {
        "brand_name": brand,
        "batch_number": batch_number.strip() or "Not detected",
        "pdp_area_cm2": pdp_area_cm2,
        "package_height_mm": package_height_mm,
        "image_quality": {
            "brightness": round(quality.brightness, 2),
            "contrast": round(quality.contrast, 2),
            "blur_variance": round(quality.blur_variance, 2),
            "warnings": quality.warnings,
        },
        "mrp_detected": mrp_match.group(1) if mrp_match else None,
        "ocr_rows": ocr_rows,
        **validation,
    }

    audit = Audit(
        inspector_id=inspector.id,
        brand_name=result["brand_name"],
        batch_number=result["batch_number"],
        compliance_status=result["status"],
        compliance_score=result["score"],
        result_json=json.dumps(result),
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    result["audit_id"] = audit.id
    result["created_at"] = audit.created_at.isoformat()
    return result


@app.get("/api/v1/audits", response_model=list[AuditSummary])
def list_audits(
    inspector: Inspector = Depends(get_current_inspector),
    db: Session = Depends(get_db),
):
    return (
        db.query(Audit)
        .filter(Audit.inspector_id == inspector.id)
        .order_by(Audit.created_at.desc())
        .limit(100)
        .all()
    )


@app.get("/api/v1/audits/{audit_id}")
def get_audit(
    audit_id: int,
    inspector: Inspector = Depends(get_current_inspector),
    db: Session = Depends(get_db),
):
    audit = (
        db.query(Audit)
        .filter(Audit.id == audit_id, Audit.inspector_id == inspector.id)
        .first()
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    payload = json.loads(audit.result_json)
    payload["audit_id"] = audit.id
    payload["created_at"] = audit.created_at.isoformat()
    return payload


@app.post("/api/v1/reports/export")
def export_report(
    audit_id: int = Form(...),
    format: str = Form(...),
    inspector: Inspector = Depends(get_current_inspector),
    db: Session = Depends(get_db),
):
    if format not in {"pdf", "csv"}:
        raise HTTPException(400, "format must be pdf or csv")

    audit = (
        db.query(Audit)
        .filter(Audit.id == audit_id, Audit.inspector_id == inspector.id)
        .first()
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    payload = json.loads(audit.result_json)
    payload["audit_id"] = audit.id
    payload["created_at"] = audit.created_at.isoformat()

    if format == "pdf":
        content = build_pdf(payload)
        return StreamingResponse(
            BytesIO(content),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="audit-{audit_id}.pdf"'},
        )

    content = build_csv(payload)
    return StreamingResponse(
        BytesIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="audit-{audit_id}.csv"'},
    )


@app.get("/api/v1/admin/config")
def get_admin_config(_: Inspector = Depends(require_senior_officer)):
    from .validator import FONT_RULE_MATRIX
    return {"font_rule_matrix": FONT_RULE_MATRIX}


@app.put("/api/v1/admin/config")
def update_admin_config(
    matrix: list[dict],
    _: Inspector = Depends(require_senior_officer),
):
    from . import validator
    cleaned = []
    for row in matrix:
        if "max_pdp_cm2" not in row or "min_font_mm" not in row:
            raise HTTPException(400, "Each rule needs max_pdp_cm2 and min_font_mm")
        cleaned.append(
            {
                "max_pdp_cm2": float(row["max_pdp_cm2"]),
                "min_font_mm": float(row["min_font_mm"]),
            }
        )
    cleaned.sort(key=lambda x: x["max_pdp_cm2"])
    validator.FONT_RULE_MATRIX[:] = cleaned
    return {"font_rule_matrix": validator.FONT_RULE_MATRIX}
