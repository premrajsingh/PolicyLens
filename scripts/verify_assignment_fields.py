#!/usr/bin/env python3
"""Verify extracted JSON against Technical Assignment field matrix."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "outputs" / "sample"

# Assignment §3–4 required FieldValue paths (schema names)
REQUIRED_PATHS: list[str] = [
    # §3A Identity
    "insurer",
    "tpa",
    # §3B Previous year
    "previous_policy.inception_renewal_date",
    "previous_policy.tenure",
    "previous_policy.previous_inception_premium",
    "previous_policy.policy_period_start",
    "previous_policy.policy_period_end",
    # §3B Structure
    "policy_structure.employee",
    "policy_structure.spouse",
    "policy_structure.children",
    "policy_structure.parents",
    "policy_structure.parents_in_law",
    "policy_structure.sum_insured_tiers",
    # §3B Demographics
    "demographics.employees",
    "demographics.spouses",
    "demographics.children",
    "demographics.parents",
    "demographics.parents_in_law",
    "demographics.total_lives_covered",
    # §4A Hospitalization
    "hospitalization.room_rent_status",
    "hospitalization.room_rent_percentage",
    "hospitalization.room_rent_monetary_maximum",
    "hospitalization.icu_status",
    "hospitalization.icu_percentage",
    "hospitalization.icu_monetary_maximum",
    "hospitalization.pre_hospitalization_days",
    "hospitalization.post_hospitalization_days",
    # §4B Maternity
    "maternity.nine_month_waiting_period_status",
    "maternity.baby_day_one_cover",
    "maternity.vaccination_coverage",
    "maternity.normal_delivery_metro_limit",
    "maternity.normal_delivery_non_metro_limit",
    "maternity.csection_metro_limit",
    "maternity.csection_non_metro_limit",
    # §4C Waiting
    "waiting_periods.initial_30_day_status",
    "waiting_periods.first_year_waiting_period_status",
    "waiting_periods.second_year_waiting_period_status",
    "waiting_periods.ped_waiting_period_status",
    # §4D Other benefits
    "other_benefits.day_care_expenses",
    "other_benefits.opd",
    "other_benefits.teleconsultation",
    "other_benefits.pharmacy_discount",
    "other_benefits.domiciliary_hospitalization",
    "other_benefits.annual_health_check_up",
    "other_benefits.modern_treatment",
    "other_benefits.bariatric_treatment",
    "other_benefits.psychiatric_treatment",
    "other_benefits.ayush_treatment",
    "other_benefits.lgbtq_coverage",
    "other_benefits.live_in_partner_coverage",
    "other_benefits.organ_donor_expenses",
    # §4E
    "infertility_and_ambulance.infertility_treatment",
    "infertility_and_ambulance.surrogacy",
    "infertility_and_ambulance.ambulance_charges",
    "infertility_and_ambulance.air_ambulance_charges",
    # §4F
    "buffer_and_waivers.corporate_buffer_limit",
    "buffer_and_waivers.disease_wise_capping",
    "buffer_and_waivers.waiver_conditions",
]


def _get(obj: dict, path: str):
    cur: object = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _is_field_value(node: object) -> bool:
    return isinstance(node, dict) and "status" in node and "evidence" in node


def check_payload(name: str, data: dict) -> list[str]:
    errors: list[str] = []
    found = 0
    for path in REQUIRED_PATHS:
        node = _get(data, path)
        if node is None:
            errors.append(f"{name}: missing path {path}")
            continue
        if not _is_field_value(node):
            errors.append(f"{name}: {path} is not a FieldValue envelope")
            continue
        if node.get("value") is not None:
            found += 1
            if not node.get("evidence"):
                errors.append(f"{name}: {path} has value but no evidence")
    fill = found / len(REQUIRED_PATHS)
    print(f"OK_KEYS {name}: fill={found}/{len(REQUIRED_PATHS)} ({fill:.0%})")
    return errors


def main() -> int:
    files = sorted(SAMPLE.glob("*.json"))
    if not files:
        print("FAIL: no outputs/sample/*.json")
        return 1
    all_errors: list[str] = []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        all_errors.extend(check_payload(path.name, data))
    if all_errors:
        print("\n".join(all_errors))
        print(f"FAIL {len(all_errors)} issues")
        return 1
    print("PASS assignment field matrix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
