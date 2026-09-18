/** Human-readable labels for assignment field paths and provider details. */

const FIELD_LABELS: Record<string, string> = {
  insurer: "Insurer",
  claims_administrator: "Claims administrator",
  policy_type: "Policy type",
  tpa: "TPA",
  policy_number: "Policy number",
  group_company_name: "Group company",
  "current_policy.policy_period_start": "Policy period start",
  "current_policy.policy_period_end": "Policy period end",
  "current_policy.inception_date": "Inception date",
  "current_policy.net_premium": "Net premium",
  "current_policy.gross_premium": "Gross premium",
  "current_policy.aggregate_sum_insured": "Aggregate sum insured",
  "previous_policy.inception_renewal_date": "Inception / renewal date",
  "previous_policy.policy_period_start": "Policy period start",
  "previous_policy.policy_period_end": "Policy period end",
  "previous_policy.tenure": "Tenure",
  "previous_policy.previous_inception_premium": "Previous inception premium",
  "previous_policy.renewal_premium": "Renewal premium",
  "previous_policy.raw_policy_period_text": "Policy period (source text)",
  "policy_structure.employee": "Employee cover",
  "policy_structure.spouse": "Spouse cover",
  "policy_structure.children": "Children cover",
  "policy_structure.parents": "Parents cover",
  "policy_structure.parents_in_law": "Parents-in-law cover",
  "policy_structure.other_family_members": "Other family members",
  "policy_structure.family_conditions": "Family conditions",
  "policy_structure.sum_insured_tiers": "Sum insured tiers",
  "demographics.employees": "Employees",
  "demographics.spouses": "Spouses",
  "demographics.children": "Children",
  "demographics.parents": "Parents",
  "demographics.parents_in_law": "Parents-in-law",
  "demographics.other_dependents": "Other dependents",
  "demographics.total_lives_covered": "Total lives covered",
  "hospitalization.room_rent_status": "Room rent status",
  "hospitalization.room_rent_percentage": "Room rent %",
  "hospitalization.room_rent_monetary_maximum": "Room rent maximum",
  "hospitalization.icu_status": "ICU status",
  "hospitalization.icu_percentage": "ICU %",
  "hospitalization.icu_monetary_maximum": "ICU maximum",
  "hospitalization.pre_hospitalization_days": "Pre-hospitalization days",
  "hospitalization.post_hospitalization_days": "Post-hospitalization days",
  "hospitalization.conditions": "Hospitalization conditions",
  "maternity.normal_delivery_limit": "Normal delivery limit",
  "maternity.csection_limit": "C-section limit",
  "maternity.nine_month_waiting_period_status": "9-month waiting period",
  "maternity.nine_month_waiting_period_conditions": "9-month waiting conditions",
  "maternity.baby_day_one_cover": "Baby day-one cover",
  "maternity.vaccination_coverage": "Vaccination coverage",
  "maternity.vaccination_limit": "Vaccination limit",
  "maternity.normal_delivery_metro_limit": "Normal delivery (metro)",
  "maternity.normal_delivery_non_metro_limit": "Normal delivery (non-metro)",
  "maternity.csection_metro_limit": "C-section (metro)",
  "maternity.csection_non_metro_limit": "C-section (non-metro)",
  "maternity.maternity_conditions": "Maternity conditions",
  "maternity.maternity_exclusions": "Maternity exclusions",
  "waiting_periods.initial_30_day_status": "Initial 30-day waiting",
  "waiting_periods.initial_30_day_conditions": "Initial 30-day conditions",
  "waiting_periods.first_year_waiting_period_status": "1st year waiting",
  "waiting_periods.second_year_waiting_period_status": "2nd year waiting",
  "waiting_periods.first_second_year_conditions": "1st/2nd year conditions",
  "waiting_periods.ped_waiting_period_status": "PED waiting period",
  "waiting_periods.ped_duration": "PED duration",
  "waiting_periods.ped_conditions": "PED conditions",
  "other_benefits.day_care_expenses": "Day-care expenses",
  "other_benefits.opd": "OPD",
  "other_benefits.teleconsultation": "Teleconsultation",
  "other_benefits.pharmacy_discount": "Pharmacy discount",
  "other_benefits.domiciliary_hospitalization": "Domiciliary hospitalization",
  "other_benefits.annual_health_check_up": "Annual health check-up",
  "other_benefits.modern_treatment": "Modern treatment",
  "other_benefits.bariatric_treatment": "Bariatric treatment",
  "other_benefits.psychiatric_treatment": "Psychiatric treatment",
  "other_benefits.ayush_treatment": "AYUSH treatment",
  "other_benefits.lgbtq_coverage": "LGBTQ coverage",
  "other_benefits.live_in_partner_coverage": "Live-in partner coverage",
  "other_benefits.organ_donor_expenses": "Organ donor expenses",
  "infertility_and_ambulance.infertility_treatment": "Infertility treatment",
  "infertility_and_ambulance.surrogacy": "Surrogacy",
  "infertility_and_ambulance.infertility_limits": "Infertility limits",
  "infertility_and_ambulance.surrogacy_limits": "Surrogacy limits",
  "infertility_and_ambulance.ambulance_charges": "Ambulance charges",
  "infertility_and_ambulance.ambulance_limits": "Ambulance limits",
  "infertility_and_ambulance.air_ambulance_charges": "Air ambulance",
  "infertility_and_ambulance.air_ambulance_limits": "Air ambulance limits",
  "infertility_and_ambulance.conditions": "Infertility & ambulance conditions",
  "buffer_and_waivers.corporate_buffer_limit": "Corporate buffer limit",
  "buffer_and_waivers.disease_wise_capping": "Disease-wise capping",
  "buffer_and_waivers.waiver_conditions": "Waiver conditions",
  "buffer_and_waivers.additional_waivers": "Additional waivers",
};

const SECTION_LABELS: Record<string, string> = {
  previous_policy: "Previous year’s policy details",
  current_policy: "Current policy schedule",
  policy_structure: "Policy structure",
  demographics: "Demographics",
  hospitalization: "Room rent & hospitalization",
  maternity: "Maternity benefits",
  waiting_periods: "Waiting periods",
  other_benefits: "Other benefits",
  infertility_and_ambulance: "Infertility & ambulance",
  buffer_and_waivers: "Buffer & waiver details",
};

export function fieldLabel(path: string): string {
  if (FIELD_LABELS[path]) return FIELD_LABELS[path];
  const leaf = path.includes(".") ? path.slice(path.lastIndexOf(".") + 1) : path;
  return leaf
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function sectionLabel(key: string): string {
  return SECTION_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Turn raw provider health detail into a short manager-friendly line. */
export function formatProviderDetail(detail: string | undefined | null): string {
  if (!detail) return "";
  const trimmed = detail.trim();
  if (!trimmed) return "";

  // Python/JSON dict-looking payloads
  if (trimmed.startsWith("{") || trimmed.startsWith("{'")) {
    try {
      const normalized = trimmed.replace(/'/g, '"');
      const obj = JSON.parse(normalized) as Record<string, unknown>;
      const parts: string[] = [];
      if (obj.model) parts.push(`Model: ${obj.model}`);
      if (obj.dimension != null) parts.push(`${obj.dimension}-dim`);
      if (obj.index) parts.push(`Index: ${obj.index}`);
      if (obj.vectors != null) parts.push(`${obj.vectors} vectors`);
      if (obj.status && parts.length === 0) parts.push(String(obj.status));
      if (parts.length) return parts.join(" · ");
    } catch {
      /* fall through */
    }
  }

  return trimmed
    .replace(/^model=/, "Model: ")
    .replace(/\bindex=/, "Index: ")
    .replace(/\bnamespace=\s*/, "Namespace: (default) ")
    .replace(/\bvectors=/, "Vectors: ")
    .replace(/\buri=/, "URI: ")
    .replace(/\bdatabase=/, "Database: ");
}

export function displayFilename(name: string | undefined | null): string {
  if (!name) return "Untitled";
  // Strip leading hash-like upload prefixes: olj4KTUo9B1546-1692687606_925469 - 00 GMC...
  const cleaned = name.replace(/^[A-Za-z0-9]{8,}[-_]\d{6,}[_-]?\d*\s*[-–—]\s*/, "");
  return cleaned.trim() || name;
}

export function isFoundStatus(status?: string | null): boolean {
  const s = (status || "").toLowerCase();
  return ["covered", "not_covered", "waived_off", "applied", "partial", "partially_covered", "conflict"].includes(
    s,
  );
}
