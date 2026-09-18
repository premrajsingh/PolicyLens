"""Document-derived consistency checks and narrow, label-based schedule readers.

These rules contain no insurer names, sample answers, filenames or policy IDs.
The LLM handles unfamiliar layouts; rules only act when a source label is explicit.
"""

from __future__ import annotations

import re

from app.extraction.normalize import normalize_currency, normalize_percentage
from app.models.schema import EvidenceItem, ExtractedPolicy, FieldValue


def _field(
    policy: ExtractedPolicy, page: int, quote: str, value, *, status="covered", conditions=None
):
    return FieldValue(
        value=value,
        normalized_value=value,
        status=status,
        raw_text=quote,
        confidence=0.95,
        conditions=conditions or [],
        evidence=[
            EvidenceItem(
                source_file=policy.document.filename,
                page_number=page,
                quote=quote,
                section="schedule",
            )
        ],
    )


def _unknown(reason: str) -> FieldValue:
    return FieldValue(warnings=[reason])


def _quotes(field: FieldValue) -> str:
    return "\n".join(e.quote for e in field.evidence)


def apply_schema_rules(policy: ExtractedPolicy, page_texts: dict[int, str]) -> ExtractedPolicy:
    # Field names are shared between current and historic groups; history needs proof.
    for key in type(policy.previous_policy).model_fields:
        field = getattr(policy.previous_policy, key)
        if field.value is not None or field.status != "unknown":
            if not re.search(
                r"\b(?:previous|prior|expiring|preceding)\s+(?:year|policy|period|inception|premium)|\blast\s+year",
                _quotes(field),
                re.I,
            ):
                setattr(policy.previous_policy, key, _unknown("historical_context_not_explicit"))
    inception = policy.current_policy.inception_date
    if inception.value is not None and not re.search(r"\binception\b", _quotes(inception), re.I):
        policy.current_policy.inception_date = _unknown("inception_not_explicit")
    for key in (
        "normal_delivery_metro_limit",
        "normal_delivery_non_metro_limit",
        "csection_metro_limit",
        "csection_non_metro_limit",
    ):
        field = getattr(policy.maternity, key)
        pattern = r"non[ -]?metro" if "non_metro" in key else r"(?<!non-)(?<!non )\bmetro\b"
        if field.value is not None and not re.search(pattern, _quotes(field), re.I):
            setattr(policy.maternity, key, _unknown("geographic_limit_not_explicit"))
    ped = policy.waiting_periods.ped_duration
    if ped.value is not None and not re.search(r"\bPED\b|pre[ -]?existing", _quotes(ped), re.I):
        policy.waiting_periods.ped_duration = _unknown("ped_duration_not_explicit")
    if policy.policy_type.value == "gpa":
        return policy

    premium_candidates = {"net_premium": [], "gross_premium": []}
    for page, body in page_texts.items():
        # Explicit labeled amounts may disagree between a schedule and a receipt.
        for key, label in (
            ("net_premium", r"Total Net premium"),
            ("gross_premium", r"Gross premium"),
        ):
            pattern = (
                rf"(?im)^{label}\s*(?:\(Rs\.?\))?\s*[:|]?\s*"
                r"(?:Rs\.?|INR|₹)?\s*([\d,]+(?:\.\d+)?)"
            )
            for match in re.finditer(pattern, body):
                amount = normalize_currency(match[1])
                if amount is not None:
                    premium_candidates[key].append((page, match[0], amount))
        # Some PDF table parsers put the merged row label after its two value rows.
        room = re.search(
            r"Normal\s+(\d+(?:\.\d+)?)%\s+ICU\s+(\d+(?:\.\d+)?)%"
            r"\s+Hospital Accommodation[^\n]*?ICU/day",
            body,
            re.I,
        )
        if room:
            for prefix, value in (("room_rent", room[1]), ("icu", room[2])):
                setattr(
                    policy.hospitalization,
                    prefix + "_status",
                    _field(policy, page, room[0], "Covered"),
                )
                setattr(
                    policy.hospitalization,
                    prefix + "_percentage",
                    _field(
                        policy,
                        page,
                        room[0],
                        float(value),
                        conditions=["Percentage of sum insured per day."],
                    ),
                )
        room_condition = re.search(
            r"If the Insured Person is admitted[^.]+eligible Room Rent\.", body
        )
        if room_condition:
            policy.hospitalization.conditions = _field(
                policy, page, room_condition[0], room_condition[0]
            )
        maternity = re.search(
            r"Normal\s+([\d,]+)\s+C[- ]Section\s+([\d,]+)\s+Maternity Expenses", body, re.I
        )
        if maternity:
            for key, amount in (
                ("normal_delivery_limit", maternity[1]),
                ("csection_limit", maternity[2]),
            ):
                setattr(
                    policy.maternity,
                    key,
                    _field(policy, page, maternity[0], normalize_currency(amount)),
                )
        maternity_conditions = re.search(
            r"Maternity Expenses 1\.[\s\S]+?Pre & Post Natal Expenses[^\n]+", body
        )
        if maternity_conditions:
            policy.maternity.maternity_conditions = _field(
                policy, page, maternity_conditions[0], maternity_conditions[0]
            )
        second_year = re.search(r"2\s*(?:yr|year) exclusions[^\n]*Waived Off", body, re.I)
        if second_year:
            policy.waiting_periods.second_year_waiting_period_status = _field(
                policy, page, second_year[0], "Waived Off", status="waived_off"
            )
            policy.waiting_periods.first_second_year_conditions = _field(
                policy, page, second_year[0], second_year[0], status="waived_off"
            )
        ambulance = re.search(
            r"Emergency Ambulance\s+INR\s+([\d,]+)\s+per hospitalization", body, re.I
        )
        if ambulance:
            policy.infertility_and_ambulance.ambulance_limits = _field(
                policy,
                page,
                ambulance[0],
                normalize_currency(ambulance[1]),
                conditions=["Per hospitalization."],
            )
        # Keep the complete paragraph/table row when the label is embedded mid-row.
        for block in re.split(r"\n\s*\n", body):
            if re.search(r"Disease wise capping", block, re.I) and re.search(r"-\s*\d{3,}", block):
                policy.buffer_and_waivers.disease_wise_capping = _field(
                    policy, page, block.strip(), block.strip()
                )
        modern = re.search(r"\d+% co-pay For cyberknife[^\n]+", body, re.I)
        if modern:
            policy.other_benefits.modern_treatment = _field(
                policy,
                page,
                modern[0],
                modern[0],
                status="partially_covered",
                conditions=["Specified procedures only; the listed co-payment applies."],
            )
        buffer = re.search(
            r"(?:We shall reimburse the Insured Person|\Afor the treatment of the Critical Illness)"
            r"[\s\S]+?(?=Premium per life|\Z)",
            body,
        )
        if buffer and policy.buffer_and_waivers.corporate_buffer_limit.value is not None:
            field = policy.buffer_and_waivers.corporate_buffer_limit
            if buffer[0].strip() not in field.conditions:
                field.conditions.append(buffer[0].strip())
            ev = EvidenceItem(
                source_file=policy.document.filename, page_number=page, quote=buffer[0].strip()
            )
            if ev not in field.evidence:
                field.evidence.append(ev)
        # A source-labeled room table identifies which column each amount belongs to.
        header = re.search(
            r"Sum Insured[^\n]*Normal Hospitali[sz]ation[^\n]*ICU Hospitali[sz]ation\s*\n",
            body,
            re.I,
        )
        if header:
            portion = body[header.end() :]
            rows = []
            eligibility = (
                r"(?:No\s+Limit|No\s+Capping|\d+(?:\.\d+)?\s*%\s+of\s+Sum\s+Insured\s+per\s+day)"
            )
            row_re = re.compile(
                rf"((?:Rs\.?|INR|₹)\s*[\d,]+)\s+({eligibility})\s+({eligibility})", re.I
            )
            for line in portion.splitlines():
                match = row_re.fullmatch(line.strip())
                if not match:
                    break
                rows.append(match)
            if rows:
                quote = header[0] + "\n".join(m[0] for m in rows)
                tiers = [normalize_currency(m[1]) for m in rows]
                policy.policy_structure.sum_insured_tiers = _field(policy, page, quote, tiers)
                # Retain proportional deduction terms from the same room section.
                room_section = body[
                    header.start() : body.find("Day Care", header.end())
                    if "Day Care" in body[header.end() :]
                    else header.end() + 1000
                ]
                conditions = [
                    m[0].strip()
                    for m in re.finditer(r"If the Insured Member[^.]+\.", room_section, re.I)
                ]
                for index, prefix in ((2, "room_rent"), (3, "icu")):
                    amounts = [m[index] for m in rows]
                    setattr(
                        policy.hospitalization,
                        prefix + "_status",
                        _field(policy, page, quote, "Covered", conditions=conditions),
                    )
                    if all(re.fullmatch(r"No\s+(?:Limit|Capping)", x, re.I) for x in amounts):
                        setattr(
                            policy.hospitalization,
                            prefix + "_monetary_maximum",
                            _field(policy, page, quote, "No Limit", conditions=conditions),
                        )
                        setattr(policy.hospitalization, prefix + "_percentage", FieldValue())
                    else:
                        percentages = [normalize_percentage(x) for x in amounts]
                        val = (
                            percentages[0]
                            if len(set(percentages)) == 1
                            else [
                                dict(sum_insured=tier, percentage=percentage)
                                for tier, percentage in zip(tiers, percentages, strict=True)
                            ]
                        )
                        setattr(
                            policy.hospitalization,
                            prefix + "_percentage",
                            _field(
                                policy,
                                page,
                                quote,
                                val,
                                conditions=[
                                    "Percentage of the applicable sum insured per day.",
                                    *conditions,
                                ],
                            ),
                        )
                        # The first column is a sum insured, not a fixed room/ICU cap.
                        setattr(
                            policy.hospitalization,
                            prefix + "_monetary_maximum",
                            FieldValue(
                                conditions=[
                                    "The source gives a percentage of sum insured; "
                                    "no separate monetary maximum is stated."
                                ]
                            ),
                        )
        # Read current premium totals from a header + immediately following numeric row.
        premium = re.search(
            r"(?m)^Premium\s+CGST\s+IGST\s+SGST\s+UGST\s+Total Premium[^\n]*\n([^\n]+)", body
        )
        if premium:
            numbers = re.findall(r"(?:`|₹|Rs\.?)\s*([\d,]+(?:\.\d+)?)", premium[1])
            if len(numbers) == 6:
                policy.current_policy.net_premium = _field(
                    policy,
                    page,
                    premium[0],
                    normalize_currency(numbers[0]),
                    conditions=["Premium excluding tax."],
                )
                policy.current_policy.gross_premium = _field(
                    policy,
                    page,
                    premium[0],
                    normalize_currency(numbers[-1]),
                    conditions=["Total premium including tax."],
                )
        dependents = re.search(r"(?m)^\s*\d*\s*Dependents\s+(\d+)\s*$", body)
        if dependents:
            policy.demographics.other_dependents = _field(
                policy,
                page,
                dependents[0].strip(),
                int(dependents[1]),
                conditions=["Combined dependents; no spouse/child/parent split is stated here."],
            )
        # Explicit PED coverage for both existing and newly joining members is a waiver
        # for those populations. It does not establish a numeric waiting duration.
        ped_coverage = re.search(
            r"Pre-existing diseases are covered for existing members and new joinees\.", body, re.I
        )
        if ped_coverage:
            policy.waiting_periods.ped_waiting_period_status = _field(
                policy,
                page,
                ped_coverage[0],
                "Waived off",
                status="waived_off",
                conditions=["Applies to existing members and new joinees."],
            )
            if policy.waiting_periods.ped_duration.value is not None:
                policy.waiting_periods.ped_duration = _unknown("ped_duration_not_explicit")
    for key, candidates in premium_candidates.items():
        if not candidates:
            continue
        amounts = {item[2] for item in candidates}
        if len(amounts) == 1:
            page, quote, amount = candidates[0]
            setattr(policy.current_policy, key, _field(policy, page, quote, amount))
        else:
            evidence = [
                EvidenceItem(source_file=policy.document.filename, page_number=page, quote=quote)
                for page, quote, _ in candidates
            ]
            setattr(
                policy.current_policy,
                key,
                FieldValue(
                    status="conflict",
                    evidence=evidence,
                    conflicts=[f"Page {page}: {amount:g}" for page, _, amount in candidates],
                    conditions=[
                        "Conflicting labeled amounts require review; no amount was selected."
                    ],
                ),
            )
    return policy
