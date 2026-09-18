from __future__ import annotations

import re
from typing import Any

from app.extraction.normalize import (
    normalize_status,
)
from app.models.schema import EvidenceItem, FieldValue

FIELD_GROUPS: dict[str, list[str]] = {
    "identity": [
        "insurer",
        "tpa",
        "claims_administrator",
        "policy_type",
        "policy_number",
        "group_company_name",
    ],
    "current_policy": [
        "policy_period_start",
        "policy_period_end",
        "inception_date",
        "net_premium",
        "gross_premium",
        "aggregate_sum_insured",
    ],
    "previous_policy": [
        "inception_renewal_date",
        "policy_period_start",
        "policy_period_end",
        "tenure",
        "previous_inception_premium",
        "renewal_premium",
        "raw_policy_period_text",
    ],
    "policy_structure": [
        "employee",
        "spouse",
        "children",
        "parents",
        "parents_in_law",
        "other_family_members",
        "family_conditions",
        "sum_insured_tiers",
    ],
    "demographics": [
        "employees",
        "spouses",
        "children",
        "parents",
        "parents_in_law",
        "other_dependents",
        "total_lives_covered",
    ],
    "room_hospitalization": [
        "room_rent_status",
        "room_rent_percentage",
        "room_rent_monetary_maximum",
        "icu_status",
        "icu_percentage",
        "icu_monetary_maximum",
        "pre_hospitalization_days",
        "post_hospitalization_days",
        "conditions",
    ],
    "maternity": [
        "normal_delivery_limit",
        "csection_limit",
        "nine_month_waiting_period_status",
        "nine_month_waiting_period_conditions",
        "baby_day_one_cover",
        "vaccination_coverage",
        "vaccination_limit",
        "normal_delivery_metro_limit",
        "normal_delivery_non_metro_limit",
        "csection_metro_limit",
        "csection_non_metro_limit",
        "maternity_conditions",
        "maternity_exclusions",
    ],
    "waiting_periods": [
        "initial_30_day_status",
        "initial_30_day_conditions",
        "first_year_waiting_period_status",
        "second_year_waiting_period_status",
        "first_second_year_conditions",
        "ped_waiting_period_status",
        "ped_duration",
        "ped_conditions",
    ],
    "other_benefits": [
        "day_care_expenses",
        "opd",
        "teleconsultation",
        "pharmacy_discount",
        "domiciliary_hospitalization",
        "annual_health_check_up",
        "modern_treatment",
        "bariatric_treatment",
        "psychiatric_treatment",
        "ayush_treatment",
        "lgbtq_coverage",
        "live_in_partner_coverage",
        "organ_donor_expenses",
    ],
    "infertility_ambulance": [
        "infertility_treatment",
        "surrogacy",
        "infertility_limits",
        "surrogacy_limits",
        "ambulance_charges",
        "ambulance_limits",
        "air_ambulance_charges",
        "air_ambulance_limits",
        "conditions",
    ],
    "buffer_waivers": [
        "corporate_buffer_limit",
        "disease_wise_capping",
        "waiver_conditions",
        "additional_waivers",
    ],
}

# Map API group names used in retrieval to schema attribute names
GROUP_ATTR = {
    "identity": None,
    "current_policy": "current_policy",
    "previous_policy": "previous_policy",
    "policy_structure": "policy_structure",
    "demographics": "demographics",
    "room_hospitalization": "hospitalization",
    "maternity": "maternity",
    "waiting_periods": "waiting_periods",
    "other_benefits": "other_benefits",
    "infertility_ambulance": "infertility_and_ambulance",
    "buffer_waivers": "buffer_and_waivers",
}


def _evidence(chunk: dict[str, Any], quote: str) -> EvidenceItem:
    return EvidenceItem(
        source_file=chunk.get("source_file", ""),
        page_number=int(chunk.get("page_number") or 0),
        quote=quote.strip()[:500],
        section=chunk.get("section", "general"),
        parser=chunk.get("parser", "text"),
        retrieval_score=chunk.get("score"),
    )


def mine_field_from_evidence(
    field_name: str, chunks: list[dict[str, Any]], *, group: str = ""
) -> FieldValue:
    """Conservative offline fallback. Never infer coverage from a heading alone."""
    labels = {
        "insurer": r"(?:Insurer|Insurance Company)",
        "tpa": r"(?:TPA|Third Party Administrator)",
        "policy_number": r"Policy (?:Number|No\.?)",
        "group_company_name": r"(?:Insured Name|Name of Policyholder|Policyholder's name)",
        "previous_inception_premium": (
            r"(?:Previous year's inception premium|Previous inception premium)"
        ),
    }
    status_patterns = {
        "nine_month_waiting_period_status": r"(?:9|nine)[ -]*months?[^.\n]{0,90}",
        "baby_day_one_cover": r"(?:new\s*born|baby)[^.\n]{0,150}",
        "vaccination_coverage": r"vaccination[^.\n]{0,100}",
        "initial_30_day_status": (
            r"(?:30[ -]*days? wait(?:ing)? period|initial waiting period)[^.\n]{0,120}"
        ),
        "first_year_waiting_period_status": r"first(?:\s*(?:&|and)\s*second)? year[^.\n]{0,120}",
        "second_year_waiting_period_status": r"(?:first\s*(?:&|and)\s*)?second year[^.\n]{0,120}",
        "ped_waiting_period_status": r"(?:PED|pre[ -]?existing(?: diseases?)?)[^.\n]{0,120}",
    }
    for chunk in chunks:
        body = chunk.get("text") or ""
        label = labels.get(field_name)
        if label:
            m = re.search(rf"\b{label}\s*:\s*([^\n|]{{2,140}})", body, re.I)
            if m:
                value = m[1].strip()
                return FieldValue(
                    value=value,
                    normalized_value=value,
                    status="covered",
                    raw_text=m[0],
                    confidence=0.65,
                    evidence=[_evidence(chunk, m[0])],
                    warnings=["deterministic_fallback"],
                )
        pattern = status_patterns.get(field_name)
        if pattern:
            for m in re.finditer(pattern, body, re.I):
                quote = m[0]
                status = normalize_status(quote)
                if (
                    status is None
                    and field_name == "baby_day_one_cover"
                    and re.search(r"day[ -]*(?:one|1).*available", quote, re.I)
                ):
                    status = "covered"
                if status:
                    return FieldValue(
                        value=status,
                        normalized_value=status,
                        status=status,
                        raw_text=quote,
                        confidence=0.65,
                        evidence=[_evidence(chunk, quote)],
                        conditions=[quote],
                        warnings=["deterministic_fallback"],
                    )
    return FieldValue()
