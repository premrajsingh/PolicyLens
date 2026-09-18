from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthStatus(BaseModel):
    name: str
    status: Literal["ok", "degraded", "error", "disabled"]
    detail: str = ""
    configured: bool = False


class EvidenceItem(BaseModel):
    source_file: str
    page_number: int
    quote: str
    section: str = "general"
    parser: Literal["text", "table", "ocr"] = "text"
    retrieval_score: float | None = None


FieldStatus = Literal[
    "covered",
    "not_covered",
    "waived_off",
    "applied",
    "not_applicable",
    "unknown",
    "conflict",
    "partially_covered",
]


class FieldValue(BaseModel):
    value: Any = None
    normalized_value: Any = None
    status: FieldStatus = "unknown"
    raw_text: str | None = None
    conditions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


def unknown_field() -> FieldValue:
    return FieldValue()


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    content_hash: str
    page_count: int = 0
    ocr_used: bool = False
    parsers: list[str] = Field(default_factory=list)


class PreviousPolicy(BaseModel):
    inception_renewal_date: FieldValue = Field(default_factory=unknown_field)
    policy_period_start: FieldValue = Field(default_factory=unknown_field)
    policy_period_end: FieldValue = Field(default_factory=unknown_field)
    tenure: FieldValue = Field(default_factory=unknown_field)
    previous_inception_premium: FieldValue = Field(default_factory=unknown_field)
    renewal_premium: FieldValue = Field(default_factory=unknown_field)
    raw_policy_period_text: FieldValue = Field(default_factory=unknown_field)


class CurrentPolicy(BaseModel):
    policy_period_start: FieldValue = Field(default_factory=unknown_field)
    policy_period_end: FieldValue = Field(default_factory=unknown_field)
    inception_date: FieldValue = Field(default_factory=unknown_field)
    net_premium: FieldValue = Field(default_factory=unknown_field)
    gross_premium: FieldValue = Field(default_factory=unknown_field)
    aggregate_sum_insured: FieldValue = Field(default_factory=unknown_field)


class PolicyStructure(BaseModel):
    employee: FieldValue = Field(default_factory=unknown_field)
    spouse: FieldValue = Field(default_factory=unknown_field)
    children: FieldValue = Field(default_factory=unknown_field)
    parents: FieldValue = Field(default_factory=unknown_field)
    parents_in_law: FieldValue = Field(default_factory=unknown_field)
    other_family_members: FieldValue = Field(default_factory=unknown_field)
    family_conditions: FieldValue = Field(default_factory=unknown_field)
    sum_insured_tiers: FieldValue = Field(default_factory=unknown_field)


class Demographics(BaseModel):
    employees: FieldValue = Field(default_factory=unknown_field)
    spouses: FieldValue = Field(default_factory=unknown_field)
    children: FieldValue = Field(default_factory=unknown_field)
    parents: FieldValue = Field(default_factory=unknown_field)
    parents_in_law: FieldValue = Field(default_factory=unknown_field)
    other_dependents: FieldValue = Field(default_factory=unknown_field)
    total_lives_covered: FieldValue = Field(default_factory=unknown_field)


class Hospitalization(BaseModel):
    room_rent_status: FieldValue = Field(default_factory=unknown_field)
    room_rent_percentage: FieldValue = Field(default_factory=unknown_field)
    room_rent_monetary_maximum: FieldValue = Field(default_factory=unknown_field)
    icu_status: FieldValue = Field(default_factory=unknown_field)
    icu_percentage: FieldValue = Field(default_factory=unknown_field)
    icu_monetary_maximum: FieldValue = Field(default_factory=unknown_field)
    pre_hospitalization_days: FieldValue = Field(default_factory=unknown_field)
    post_hospitalization_days: FieldValue = Field(default_factory=unknown_field)
    conditions: FieldValue = Field(default_factory=unknown_field)


class Maternity(BaseModel):
    normal_delivery_limit: FieldValue = Field(default_factory=unknown_field)
    csection_limit: FieldValue = Field(default_factory=unknown_field)
    nine_month_waiting_period_status: FieldValue = Field(default_factory=unknown_field)
    nine_month_waiting_period_conditions: FieldValue = Field(default_factory=unknown_field)
    baby_day_one_cover: FieldValue = Field(default_factory=unknown_field)
    vaccination_coverage: FieldValue = Field(default_factory=unknown_field)
    vaccination_limit: FieldValue = Field(default_factory=unknown_field)
    normal_delivery_metro_limit: FieldValue = Field(default_factory=unknown_field)
    normal_delivery_non_metro_limit: FieldValue = Field(default_factory=unknown_field)
    csection_metro_limit: FieldValue = Field(default_factory=unknown_field)
    csection_non_metro_limit: FieldValue = Field(default_factory=unknown_field)
    maternity_conditions: FieldValue = Field(default_factory=unknown_field)
    maternity_exclusions: FieldValue = Field(default_factory=unknown_field)


class WaitingPeriods(BaseModel):
    initial_30_day_status: FieldValue = Field(default_factory=unknown_field)
    initial_30_day_conditions: FieldValue = Field(default_factory=unknown_field)
    first_year_waiting_period_status: FieldValue = Field(default_factory=unknown_field)
    second_year_waiting_period_status: FieldValue = Field(default_factory=unknown_field)
    first_second_year_conditions: FieldValue = Field(default_factory=unknown_field)
    ped_waiting_period_status: FieldValue = Field(default_factory=unknown_field)
    ped_duration: FieldValue = Field(default_factory=unknown_field)
    ped_conditions: FieldValue = Field(default_factory=unknown_field)


class OtherBenefits(BaseModel):
    day_care_expenses: FieldValue = Field(default_factory=unknown_field)
    opd: FieldValue = Field(default_factory=unknown_field)
    teleconsultation: FieldValue = Field(default_factory=unknown_field)
    pharmacy_discount: FieldValue = Field(default_factory=unknown_field)
    domiciliary_hospitalization: FieldValue = Field(default_factory=unknown_field)
    annual_health_check_up: FieldValue = Field(default_factory=unknown_field)
    modern_treatment: FieldValue = Field(default_factory=unknown_field)
    bariatric_treatment: FieldValue = Field(default_factory=unknown_field)
    psychiatric_treatment: FieldValue = Field(default_factory=unknown_field)
    ayush_treatment: FieldValue = Field(default_factory=unknown_field)
    lgbtq_coverage: FieldValue = Field(default_factory=unknown_field)
    live_in_partner_coverage: FieldValue = Field(default_factory=unknown_field)
    organ_donor_expenses: FieldValue = Field(default_factory=unknown_field)


class InfertilityAndAmbulance(BaseModel):
    infertility_treatment: FieldValue = Field(default_factory=unknown_field)
    surrogacy: FieldValue = Field(default_factory=unknown_field)
    infertility_limits: FieldValue = Field(default_factory=unknown_field)
    surrogacy_limits: FieldValue = Field(default_factory=unknown_field)
    ambulance_charges: FieldValue = Field(default_factory=unknown_field)
    ambulance_limits: FieldValue = Field(default_factory=unknown_field)
    air_ambulance_charges: FieldValue = Field(default_factory=unknown_field)
    air_ambulance_limits: FieldValue = Field(default_factory=unknown_field)
    conditions: FieldValue = Field(default_factory=unknown_field)


class BufferAndWaivers(BaseModel):
    corporate_buffer_limit: FieldValue = Field(default_factory=unknown_field)
    disease_wise_capping: FieldValue = Field(default_factory=unknown_field)
    waiver_conditions: FieldValue = Field(default_factory=unknown_field)
    additional_waivers: FieldValue = Field(default_factory=unknown_field)


class ExtractionMetadata(BaseModel):
    provider: str
    model: str | None = None
    generated_at: str
    processing_duration_seconds: float = 0.0
    pinecone_indexing_status: str = "unknown"
    neo4j_sync_status: str = "unknown"
    retrieval_method: str = "hybrid"
    ocr_used: bool = False
    parsers_used: list[str] = Field(default_factory=list)
    extraction_errors: list[str] = Field(default_factory=list)
    completion_status: Literal["complete", "partial", "offline"] = "complete"
    source_aliases: list[str] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    overall_confidence: float = 0.0
    evidence_coverage: float = 0.0
    fields_found: int = 0
    fields_missing: int = 0
    fields_requiring_review: int = 0
    conflict_count: int = 0
    extraction_warnings: list[str] = Field(default_factory=list)
    schema_valid: bool = True
    fields_not_applicable: int = 0
    field_completeness: float = 0.0
    confidence_note: str = "Model confidence is not measured extraction accuracy."


class ExtractedPolicy(BaseModel):
    schema_version: str
    pipeline_version: str
    document: DocumentInfo
    insurer: FieldValue = Field(default_factory=unknown_field)
    tpa: FieldValue = Field(default_factory=unknown_field)
    claims_administrator: FieldValue = Field(default_factory=unknown_field)
    policy_type: FieldValue = Field(default_factory=unknown_field)
    policy_number: FieldValue = Field(default_factory=unknown_field)
    group_company_name: FieldValue = Field(default_factory=unknown_field)
    previous_policy: PreviousPolicy = Field(default_factory=PreviousPolicy)
    current_policy: CurrentPolicy = Field(default_factory=CurrentPolicy)
    policy_structure: PolicyStructure = Field(default_factory=PolicyStructure)
    demographics: Demographics = Field(default_factory=Demographics)
    hospitalization: Hospitalization = Field(default_factory=Hospitalization)
    maternity: Maternity = Field(default_factory=Maternity)
    waiting_periods: WaitingPeriods = Field(default_factory=WaitingPeriods)
    other_benefits: OtherBenefits = Field(default_factory=OtherBenefits)
    infertility_and_ambulance: InfertilityAndAmbulance = Field(
        default_factory=InfertilityAndAmbulance
    )
    buffer_and_waivers: BufferAndWaivers = Field(default_factory=BufferAndWaivers)
    extraction_metadata: ExtractionMetadata
    validation: ValidationSummary = Field(default_factory=ValidationSummary)
