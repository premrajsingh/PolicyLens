from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# Only explicit monetary amounts or a standalone numeric field are currencies.
MONEY = re.compile(
    r"(?:(?:₹|`|\bRs\.?|\bINR)\s*)?(\d[\d,]*(?:\.\d+)?)\s*(crores?|lakhs?|lacs?|thousand|k)?", re.I
)


def normalize_currency(text: str | None) -> float | None:
    if not text:
        return None
    text = text.strip()
    match = MONEY.fullmatch(text)
    if not match:
        match = re.search(
            r"(?:₹|`|\bRs\.?|\bINR)\s*(\d[\d,]*(?:\.\d+)?)\s*(crores?|lakhs?|lacs?|thousand|k)?\b",
            text,
            re.I,
        )
    if not match:
        match = re.search(r"\b(\d[\d,]*(?:\.\d+)?)\s*(crores?|lakhs?|lacs?|thousand)\b", text, re.I)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    factor = (
        10_000_000
        if unit.startswith("crore")
        else 100_000
        if unit.startswith(("lakh", "lac"))
        else 1_000
        if unit in {"thousand", "k"}
        else 1
    )
    return amount * factor


def normalize_percentage(text: str | None) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text or "")
    return float(m.group(1)) if m else None


def normalize_duration(text: str | None) -> dict[str, Any] | None:
    words = {
        "thirty": 30,
        "sixty": 60,
        "nine": 9,
        "one": 1,
        "two": 2,
        "three": 3,
        "first": 1,
        "second": 2,
    }
    m = re.search(
        r"\b(\d+|thirty|sixty|nine|one|two|three|first|second)[ -]+(days?|months?|years?)\b",
        text or "",
        re.I,
    )
    if not m:
        return None
    amount = int(m[1]) if m[1].isdigit() else words[m[1].lower()]
    return {"value": amount, "unit": m[2].lower().rstrip("s") + "s"}


def normalize_date(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", text, flags=re.I)
    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b",
        r"\b\d{1,2}[- ]+[A-Za-z]+[- ]+\d{4}\b",
        r"\b[A-Za-z]+ \d{1,2}, \d{4}\b",
    ]
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %B %Y",
        "%d %b %Y",
        "%d-%B-%Y",
        "%d-%b-%Y",
        "%B %d, %Y",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, cleaned):
            for fmt in formats:
                try:
                    return datetime.strptime(match[0], fmt).date().isoformat()
                except ValueError:
                    pass
    return None


def normalize_status(text: str | None) -> str | None:
    lower = (text or "").lower().replace("_", " ")
    if re.search(r"\b(?:not waived|waiver not applicable|waiver does not apply)\b", lower):
        return "applied"
    if re.search(r"\b(?:not applicable|n/?a)\b", lower):
        return "not_applicable"
    if re.search(r"\b(?:waived(?: off)?|waiver applies)\b", lower):
        return "waived_off"
    if re.search(r"\b(?:not payable|not covered|excluded|outside the scope)\b", lower):
        return "not_covered"
    if re.search(r"\b(?:covered|covred|payable)\b", lower):
        return "covered"
    if re.search(r"\b(?:applicable|applies|applied)\b", lower):
        return "applied"
    return None


def normalize_field(field_name: str, field):
    """Never normalize a policy number, date or day count as money."""
    if field.value is None:
        field.normalized_value = None
        return field
    value = field.value
    if not isinstance(value, str):
        field.normalized_value = value if field.normalized_value is None else field.normalized_value
        return field
    result = None
    if any(s in field_name for s in ("date", "period_start", "period_end")):
        result = normalize_date(value)
    elif "percentage" in field_name:
        result = normalize_percentage(value)
    elif field_name.endswith("_days"):
        duration = normalize_duration(value)
        result = duration["value"] if duration and duration["unit"] == "days" else None
    elif any(s in field_name for s in ("duration", "tenure")):
        result = normalize_duration(value)
    elif any(s in field_name for s in ("premium", "_limit", "_maximum", "aggregate_sum_insured")):
        result = normalize_currency(value)
    if result is not None:
        field.normalized_value = result
    elif field.normalized_value is None:
        field.normalized_value = value
    return field
