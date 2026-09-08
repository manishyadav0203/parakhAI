from datetime import datetime, timezone
from sqlalchemy import DateTime, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Inspector(Base):
    __tablename__ = "inspectors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspector_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    official_email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    department_zone: Mapped[str] = mapped_column(String(160))
    designation: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), default="inspector")
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    audits: Mapped[list["Audit"]] = relationship(back_populates="inspector")


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inspector_id: Mapped[int] = mapped_column(ForeignKey("inspectors.id"))
    brand_name: Mapped[str] = mapped_column(String(160), default="Unknown")
    batch_number: Mapped[str] = mapped_column(String(120), default="Not detected")
    compliance_status: Mapped[str] = mapped_column(String(30))
    compliance_score: Mapped[int] = mapped_column(Integer)
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    inspector: Mapped[Inspector] = relationship(back_populates="audits")
