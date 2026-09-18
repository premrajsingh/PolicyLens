from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from app.models.schema import ExtractedPolicy, FieldValue, ValidationSummary


def _iter_fields(policy: ExtractedPolicy) -> Iterable[tuple[str, FieldValue]]:
    for name in type(policy).model_fields:
        obj = getattr(policy, name)
        if isinstance(obj, FieldValue):
            yield name, obj
        elif hasattr(obj, "model_fields"):
            for key in type(obj).model_fields:
                child = getattr(obj, key)
                if isinstance(child, FieldValue):
                    yield f"{name}.{key}", child


def _normalize_ws(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(
        str.maketrans({"‑": "-", "–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"'})
    )
    return re.sub(r"\s+", " ", text).strip().casefold()


def evidence_quote_in_pages(quote: str, page_texts: dict[int, str]) -> bool:
    q = _normalize_ws(quote)
    return len(q) >= 3 and any(q in _normalize_ws(text) for text in page_texts.values())


def evidence_quote_supported(quote: str, page_texts: dict[int, str], value: object = None) -> bool:
    # A number elsewhere in the document is never proof of a quoted clause.
    return evidence_quote_in_pages(quote, page_texts)


def _clear(field: FieldValue, reason: str) -> None:
    field.value = None
    field.normalized_value = None
    field.status = "unknown"
    field.confidence = 0
    field.warnings = list(dict.fromkeys([*field.warnings, reason]))


def validate_and_score(
    policy: ExtractedPolicy, *, page_texts: dict[int, str], source_file: str
) -> ExtractedPolicy:
    warnings = []
    found = missing = review = conflicts = not_applicable = supported = candidates = 0
    confidences = []
    fields = list(_iter_fields(policy))
    for path, field in fields:
        # Validate status-only claims too. Never resurrect a rejected field from raw_text.
        has_claim = field.value is not None or field.status != "unknown"
        if has_claim:
            candidates += 1
            valid = bool(field.evidence)
            for ev in field.evidence:
                if ev.source_file != source_file:
                    valid = False
                    field.warnings.append("evidence_source_mismatch")
                if ev.page_number not in page_texts:
                    valid = False
                    field.warnings.append("invalid_evidence_page")
                elif not evidence_quote_in_pages(
                    ev.quote, {ev.page_number: page_texts[ev.page_number]}
                ):
                    valid = False
                    field.warnings.append("evidence_quote_not_found")
            if not valid:
                _clear(field, "unsupported_claim")
                warnings.append(f"{path}: evidence failed validation")
            else:
                supported += 1
        if field.conflicts and field.evidence and field.status != "unknown":
            field.status = "conflict"
            field.value = field.normalized_value = None
        if field.status == "conflict":
            conflicts += 1
            review += 1
            missing += 1
        elif field.status == "not_applicable":
            not_applicable += 1
        elif field.value is not None or field.status in {
            "covered",
            "not_covered",
            "waived_off",
            "applied",
            "partially_covered",
        }:
            found += 1
            confidences.append(field.confidence)
            if field.confidence < 0.7 or field.warnings:
                review += 1
        else:
            missing += 1
            if field.warnings:
                review += 1
        field.warnings = list(dict.fromkeys(field.warnings))

    for group_name in ("current_policy", "previous_policy"):
        group = getattr(policy, group_name)
        start, end = group.policy_period_start, group.policy_period_end
        if (
            isinstance(start.normalized_value, str)
            and isinstance(end.normalized_value, str)
            and start.normalized_value > end.normalized_value
        ):
            warnings.append(f"{group_name}: policy_period_start_after_end")
            start.warnings.append("date_order")
            end.warnings.append("date_order")
            review += 1
    if policy.extraction_metadata.extraction_errors:
        warnings.extend(policy.extraction_metadata.extraction_errors)
    policy.validation = ValidationSummary(
        overall_confidence=round(sum(confidences) / len(confidences), 4) if confidences else 0,
        evidence_coverage=round(supported / candidates, 4) if candidates else 0,
        field_completeness=round(found / (len(fields) - not_applicable), 4)
        if len(fields) > not_applicable
        else 0,
        fields_found=found,
        fields_missing=missing,
        fields_not_applicable=not_applicable,
        fields_requiring_review=review,
        conflict_count=conflicts,
        extraction_warnings=warnings,
    )
    return policy


def enforce_no_hallucination(field: FieldValue) -> FieldValue:
    if (field.value is not None or field.status != "unknown") and not field.evidence:
        _clear(field, "no_evidence")
    return field
