from __future__ import annotations

import csv
import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors


def build_pdf(audit: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("LEGAL METROLOGY COMPLIANCE SCANNER", styles["Title"]))
    story.append(Paragraph("Non-Compliance / Inspection Assistance Report", styles["Heading2"]))
    story.append(Spacer(1, 8))

    summary = [
        ["Audit ID", str(audit["audit_id"])],
        ["Brand", audit["brand_name"]],
        ["Batch", audit["batch_number"]],
        ["Status", audit["status"]],
        ["Compliance Score", f'{audit["score"]}%'],
        ["PDP Area", f'{audit["pdp_area_cm2"]:.2f} cm²'],
        ["Package Real Height", f'{audit["package_height_mm"]:.2f} mm'],
        ["Required Font Height", f'{audit["required_font_mm"]:.2f} mm'],
    ]
    table = Table(summary, colWidths=[55 * mm, 110 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F1F5F9")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Extracted Text", styles["Heading3"]))
    raw_text = " ".join(row["text"] for row in audit["ocr_rows"]) or "No text detected."
    story.append(Paragraph(raw_text.replace("&", "&amp;"), styles["BodyText"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Compliance Checklist", styles["Heading3"]))
    rows = [["Declaration", "Status", "Measured", "Required"]]
    for check in audit["checks"]:
        rows.append(
            [
                check["field"],
                check["status"],
                f'{check["font_height_mm"]:.2f} mm',
                f'{check["required_font_mm"]:.2f} mm',
            ]
        )
    check_table = Table(rows, repeatRows=1, colWidths=[72 * mm, 25 * mm, 35 * mm, 35 * mm])
    check_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F172A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
                ("PADDING", (0, 0), (-1, -1), 5),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story.append(check_table)
    story.append(Spacer(1, 12))

    story.append(Paragraph("Violations", styles["Heading3"]))
    if audit["violations"]:
        for violation in audit["violations"]:
            story.append(Paragraph("• " + violation, styles["BodyText"]))
    else:
        story.append(Paragraph("No violations identified by the configured prototype checks.", styles["BodyText"]))

    story.append(Spacer(1, 30))
    story.append(Paragraph("Inspector Signature: ______________________________", styles["BodyText"]))
    story.append(Paragraph("Designation / Zone: _______________________________", styles["BodyText"]))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "This prototype report is intended to assist inspection workflow and requires human verification before official enforcement.",
            styles["Italic"],
        )
    )

    doc.build(story)
    return buffer.getvalue()


def build_csv(audit: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "audit_id",
            "timestamp",
            "brand_name",
            "batch_number",
            "compliance_status",
            "compliance_score",
            "pdp_area_cm2",
            "package_height_mm",
            "required_font_mm",
            "violation_flags",
        ]
    )
    writer.writerow(
        [
            audit["audit_id"],
            audit["created_at"],
            audit["brand_name"],
            audit["batch_number"],
            audit["status"],
            audit["score"],
            audit["pdp_area_cm2"],
            audit["package_height_mm"],
            audit["required_font_mm"],
            " | ".join(audit["violations"]),
        ]
    )
    return buffer.getvalue().encode("utf-8")
