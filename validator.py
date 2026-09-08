from __future__ import annotations

import re
from typing import Iterable


# Configurable baseline matrix for the prototype.
# Confirm against the currently applicable Legal Metrology notification/rules
# for the exact commodity/category before enforcement use.
FONT_RULE_MATRIX = [
    {"max_pdp_cm2": 100, "min_font_mm": 1.0},
    {"max_pdp_cm2": 500, "min_font_mm": 1.5},
    {"max_pdp_cm2": 1000, "min_font_mm": 2.0},
    {"max_pdp_cm2": float("inf"), "min_font_mm": 3.0},
]


DECLARATION_PATTERNS = {
    "MRP": [r"\bmrp\b", r"maximum\s+retail\s+price"],
    "Net Quantity": [r"net\s*(quantity|qty)", r"\bnet\s*w?t\b", r"\b\d+(?:\.\d+)?\s*(g|kg|ml|l)\b"],
    "Country of Origin": [r"country\s+of\s+origin", r"made\s+in\s+(india|[a-z]+)"],
    "Manufacturer Details": [r"manufactured\s+by", r"manufacturer", r"mfg\.?\s*by"],
    "Consumer Care Details": [r"consumer\s*(care|complaints?)", r"customer\s*care", r"helpline"],
    "Date of Manufacture/Packing": [r"date\s*of\s*(mfg|manufacture|packing|pack)", r"mfg\.?\s*date", r"packed\s*on"],
}


def required_font_mm(pdp_area_cm2: float) -> float:
    for row in FONT_RULE_MATRIX:
        if pdp_area_cm2 <= row["max_pdp_cm2"]:
            return row["min_font_mm"]
    return FONT_RULE_MATRIX[-1]["min_font_mm"]


def _contains(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def identify_declarations(ocr_rows: list[dict]) -> dict:
    combined = " ".join(row["text"] for row in ocr_rows)
    return {
        field: _contains(combined, patterns)
        for field, patterns in DECLARATION_PATTERNS.items()
    }


def audit_package(pdp_area_cm2: float, ocr_rows: list[dict]) -> dict:
    required_mm = required_font_mm(pdp_area_cm2)
    declarations = identify_declarations(ocr_rows)

    # For each declaration found, use its measured height. Missing declarations
    # remain a declaration failure rather than being silently inferred.
    declaration_rows = []
    for field, present in declarations.items():
        candidates = [
            row for row in ocr_rows
            if _contains(row["text"], DECLARATION_PATTERNS[field])
        ]
        measured = max((row["font_height_mm"] for row in candidates), default=0.0)
        declaration_rows.append(
            {
                "field": field,
                "present": present,
                "font_height_mm": round(measured, 3),
                "required_font_mm": required_mm,
                "font_compliant": measured >= required_mm if present else False,
                "status": "PASS" if present and measured >= required_mm else "FAIL",
            }
        )

    checks = declaration_rows + [
        {
            "field": "Minimum Font Height Compliance",
            "present": all(row["font_compliant"] for row in declaration_rows),
            "font_height_mm": min(
                (row["font_height_mm"] for row in declaration_rows),
                default=0.0,
            ),
            "required_font_mm": required_mm,
            "font_compliant": all(row["font_compliant"] for row in declaration_rows),
            "status": "PASS" if all(row["font_compliant"] for row in declaration_rows) else "FAIL",
        }
    ]

    passed = sum(1 for row in checks if row["status"] == "PASS")
    score = round((passed / len(checks)) * 100) if checks else 0

    violations = [
        f'{row["field"]}: {"missing declaration" if not row["present"] else f"font {row["font_height_mm"]:.2f} mm < required {row["required_font_mm"]:.2f} mm"}'
        for row in checks
        if row["status"] == "FAIL"
    ]

    return {
        "required_font_mm": required_mm,
        "checks": checks,
        "score": score,
        "status": "COMPLIANT" if not violations else "NON_COMPLIANT",
        "violations": violations,
    }
