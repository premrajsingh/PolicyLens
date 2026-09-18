#!/usr/bin/env node
/**
 * Assignment page + field audit.
 * Scores live API extractions against the 58 REQUIRED_PATHS and spot-checks UI routes.
 * Writes outputs/ui_audit/ASSIGNMENT_GAP.md
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const API = process.env.API_BASE || "http://127.0.0.1:8000";
const FE = process.env.FE_BASE || "http://127.0.0.1:5173";
const OUT = join(ROOT, "outputs", "ui_audit");

const REQUIRED_PATHS = [
  "insurer",
  "tpa",
  "previous_policy.inception_renewal_date",
  "previous_policy.tenure",
  "previous_policy.previous_inception_premium",
  "previous_policy.policy_period_start",
  "previous_policy.policy_period_end",
  "policy_structure.employee",
  "policy_structure.spouse",
  "policy_structure.children",
  "policy_structure.parents",
  "policy_structure.parents_in_law",
  "policy_structure.sum_insured_tiers",
  "demographics.employees",
  "demographics.spouses",
  "demographics.children",
  "demographics.parents",
  "demographics.parents_in_law",
  "demographics.total_lives_covered",
  "hospitalization.room_rent_status",
  "hospitalization.room_rent_percentage",
  "hospitalization.room_rent_monetary_maximum",
  "hospitalization.icu_status",
  "hospitalization.icu_percentage",
  "hospitalization.icu_monetary_maximum",
  "hospitalization.pre_hospitalization_days",
  "hospitalization.post_hospitalization_days",
  "maternity.nine_month_waiting_period_status",
  "maternity.baby_day_one_cover",
  "maternity.vaccination_coverage",
  "maternity.normal_delivery_metro_limit",
  "maternity.normal_delivery_non_metro_limit",
  "maternity.csection_metro_limit",
  "maternity.csection_non_metro_limit",
  "waiting_periods.initial_30_day_status",
  "waiting_periods.first_year_waiting_period_status",
  "waiting_periods.second_year_waiting_period_status",
  "waiting_periods.ped_waiting_period_status",
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
  "infertility_and_ambulance.infertility_treatment",
  "infertility_and_ambulance.surrogacy",
  "infertility_and_ambulance.ambulance_charges",
  "infertility_and_ambulance.air_ambulance_charges",
  "buffer_and_waivers.corporate_buffer_limit",
  "buffer_and_waivers.disease_wise_capping",
  "buffer_and_waivers.waiver_conditions",
];

const SECTIONS = {
  identity: ["insurer", "tpa"],
  previous_policy: REQUIRED_PATHS.filter((p) => p.startsWith("previous_policy.")),
  policy_structure: REQUIRED_PATHS.filter((p) => p.startsWith("policy_structure.")),
  demographics: REQUIRED_PATHS.filter((p) => p.startsWith("demographics.")),
  hospitalization: REQUIRED_PATHS.filter((p) => p.startsWith("hospitalization.")),
  maternity: REQUIRED_PATHS.filter((p) => p.startsWith("maternity.")),
  waiting_periods: REQUIRED_PATHS.filter((p) => p.startsWith("waiting_periods.")),
  other_benefits: REQUIRED_PATHS.filter((p) => p.startsWith("other_benefits.")),
  infertility: REQUIRED_PATHS.filter((p) => p.startsWith("infertility_and_ambulance.")),
  buffer: REQUIRED_PATHS.filter((p) => p.startsWith("buffer_and_waivers.")),
};

function getPath(obj, path) {
  let cur = obj;
  for (const part of path.split(".")) {
    if (!cur || typeof cur !== "object" || !(part in cur)) return null;
    cur = cur[part];
  }
  return cur;
}

function isFilled(node) {
  return node && typeof node === "object" && node.value != null && node.value !== "";
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} → ${res.status}`);
  return res.json();
}

function scorePayload(payload) {
  const filled = [];
  const missing = [];
  for (const path of REQUIRED_PATHS) {
    const node = getPath(payload, path);
    if (isFilled(node)) filled.push(path);
    else missing.push(path);
  }
  const bySection = {};
  for (const [name, paths] of Object.entries(SECTIONS)) {
    const f = paths.filter((p) => filled.includes(p)).length;
    bySection[name] = { filled: f, total: paths.length };
  }
  return {
    filled: filled.length,
    total: REQUIRED_PATHS.length,
    pct: Math.round((filled.length / REQUIRED_PATHS.length) * 100),
    bySection,
    missing,
  };
}

async function auditApi() {
  const docs = (await fetchJson(`${API}/api/documents`)).documents || [];
  const rows = [];
  for (const doc of docs) {
    if (doc.status === "duplicate") continue;
    let payload = null;
    try {
      payload = await fetchJson(`${API}/api/policies/${doc.id}/extraction`);
    } catch {
      rows.push({
        id: doc.id,
        name: doc.original_filename || doc.filename,
        status: doc.extraction_status,
        error: "no extraction",
        score: null,
      });
      continue;
    }
    rows.push({
      id: doc.id,
      name: doc.original_filename || doc.filename,
      status: doc.extraction_status,
      score: scorePayload(payload),
    });
  }
  return rows;
}

async function auditUi() {
  const findings = [];
  let browser;
  try {
    const exe = join(
      process.env.HOME || "",
      "Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell",
    );
    browser = await chromium.launch(
      existsSync(exe) ? { headless: true, executablePath: exe } : { headless: true },
    );
  } catch (e) {
    return [{ route: "*", issue: `playwright launch failed: ${e.message}` }];
  }
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const routes = [
    "/",
    "/workspace",
    "/evidence",
    "/knowledge-base",
    "/settings",
    "/compare",
  ];
  for (const route of routes) {
    try {
      await page.goto(`${FE}${route}`, { waitUntil: "networkidle", timeout: 30000 });
      await page.waitForTimeout(1500);
      const body = await page.locator("body").innerText();
      if (
        (route === "/workspace" || route === "/evidence") &&
        /Select a document from the dropdown/i.test(body)
      ) {
        findings.push({ route, issue: "empty document select cold-start" });
      }
      if (route === "/workspace" && !/Insurer|Policy extraction|Insurer & TPA|Policy details/i.test(body)) {
        findings.push({ route, issue: "workspace missing extraction overview" });
      }
      if (/\bActivity\b/i.test(body) || /llm_error/i.test(body)) {
        findings.push({ route, issue: "engineer clutter (Activity / llm_error) visible" });
      }
      if (/Knowledge Graph/i.test(body)) {
        findings.push({ route, issue: "Knowledge Graph still in UI" });
      }
      if (route === "/settings" && /\{\s*'name':\s*'huggingface/i.test(body)) {
        findings.push({ route, issue: "raw HF dict in settings" });
      }
      if (route === "/compare" && /Select document…/i.test(body) && !/First policy/i.test(body)) {
        findings.push({ route, issue: "compare empty" });
      }
    } catch (e) {
      findings.push({ route, issue: e.message });
    }
  }
  // /graph should redirect to workspace
  try {
    await page.goto(`${FE}/graph`, { waitUntil: "networkidle", timeout: 30000 });
    if (!page.url().includes("/workspace")) {
      findings.push({ route: "/graph", issue: "did not redirect to /workspace" });
    }
  } catch (e) {
    findings.push({ route: "/graph", issue: e.message });
  }
  await browser.close();
  return findings;
}

function scoreSamplesUnused() {
  return null;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const apiRows = await auditApi();
  const uiFindings = await auditUi();

  const { readdirSync } = await import("fs");
  const sampleDir = join(ROOT, "outputs", "sample");
  const samples = existsSync(sampleDir)
    ? readdirSync(sampleDir)
        .filter((f) => f.endsWith(".json"))
        .map((f) => {
          const payload = JSON.parse(readFileSync(join(sampleDir, f), "utf8"));
          return { file: f, score: scorePayload(payload) };
        })
    : [];

  const lines = [
    "# Assignment gap report",
    "",
    `Generated: ${new Date().toISOString()}`,
    "",
    "## Live API documents",
    "",
  ];

  for (const row of apiRows) {
    if (!row.score) {
      lines.push(`- **${row.name}**: ${row.error || row.status}`);
      continue;
    }
    const s = row.score;
    lines.push(`### ${row.name}`);
    lines.push(`- Fill: **${s.filled}/${s.total} (${s.pct}%)**`);
    for (const [sec, v] of Object.entries(s.bySection)) {
      lines.push(`  - ${sec}: ${v.filled}/${v.total}`);
    }
    lines.push("");
  }

  lines.push("## Sample outputs", "");
  for (const s of samples) {
    lines.push(`- \`${s.file}\`: ${s.score.filled}/${s.score.total} (${s.score.pct}%)`);
    lines.push(
      `  - maternity ${s.score.bySection.maternity.filled}/${s.score.bySection.maternity.total}, waiting ${s.score.bySection.waiting_periods.filled}/${s.score.bySection.waiting_periods.total}`,
    );
  }

  lines.push("", "## UI findings", "");
  if (uiFindings.length === 0) lines.push("- None (cold-start / raw dumps checks passed)");
  else uiFindings.forEach((f) => lines.push(`- \`${f.route}\`: ${f.issue}`));

  lines.push("## Ranked gaps / gates", "");
  const care = samples.find((s) => /^1\.Policy_Copy\.json$/i.test(s.file));
  const gaps = [];
  if (care) {
    if (care.score.bySection.maternity.filled < 5)
      gaps.push(`Care maternity ${care.score.bySection.maternity.filled}/7 < 5`);
    if (care.score.bySection.waiting_periods.filled < 4)
      gaps.push(`Care waiting ${care.score.bySection.waiting_periods.filled}/4 < 4`);
  } else {
    gaps.push("No Care/1.Policy_Copy sample found");
  }
  for (const f of uiFindings) gaps.push(`UI ${f.route}: ${f.issue}`);

  if (gaps.length === 0) lines.push("- **ALL GATES PASS**");
  else gaps.forEach((g, i) => lines.push(`${i + 1}. ${g}`));

  const md = lines.join("\n") + "\n";
  writeFileSync(join(OUT, "ASSIGNMENT_GAP.md"), md);
  console.log(md);
  console.log(gaps.length === 0 ? "GATE_PASS" : `GATE_FAIL ${gaps.length}`);
  process.exit(gaps.length === 0 ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
