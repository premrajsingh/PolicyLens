#!/usr/bin/env node
/**
 * Playwright loop: walk Technical Assignment Workspace tabs, screenshot, assert.
 * Exit 0 only when all checks pass.
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync, existsSync } from "fs";
import { join } from "path";

const FE = process.env.FE_BASE || "http://127.0.0.1:5173";
const API = process.env.API_BASE || "http://127.0.0.1:8000";
const OUT = join(process.cwd(), "outputs", "ui_audit");
mkdirSync(OUT, { recursive: true });

function chromiumLaunchOptions() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_PATH,
    join(
      process.env.HOME || "",
      "Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell",
    ),
  ].filter(Boolean);
  for (const path of candidates) {
    if (existsSync(path)) return { headless: true, executablePath: path };
  }
  return { headless: true };
}

const TABS = [
  { name: /Insurer & TPA/i, slug: "3a-insurer-tpa", expect: /Insurer|TPA/i },
  { name: /Policy details/i, slug: "3b-policy-details", expect: /Current|Previous|premium|period|inception/i },
  { name: /Policy Structure/i, slug: "3b-structure", expect: /Policy structure|Employee|Sum insured/i },
  { name: /Demographics/i, slug: "3b-demographics", expect: /Demographics|Employees|lives/i },
  { name: /Room.*Hospitalization/i, slug: "4a-hospitalization", expect: /Room|ICU|Hospitalization/i },
  { name: /Maternity/i, slug: "4b-maternity", expect: /Maternity|9-month|Baby|waiting/i },
  { name: /Waiting Periods/i, slug: "4c-waiting", expect: /Waiting|30-day|PED/i },
  { name: /Other Benefits/i, slug: "4d-other", expect: /Other benefits|OPD|Day/i },
  { name: /Infertility.*Ambulance/i, slug: "4e-infertility", expect: /Infertility|Ambulance/i },
  { name: /Buffer.*Waiver/i, slug: "4f-buffer", expect: /Buffer|Waiver/i },
  { name: /Evidence/i, slug: "evidence", expect: /Evidence|Page|quote|Value|source/i },
  { name: /QMS JSON/i, slug: "5-json", expect: /JSON|Export|schema_version|insurer/i },
];

async function pickGhiId() {
  const res = await fetch(`${API}/api/documents`);
  const data = await res.json();
  const docs = data.documents || [];
  const ghi = docs.find((d) => /ghi/i.test(d.original_filename || d.filename));
  const care = docs.find((d) => /1\.Policy/i.test(d.original_filename || d.filename));
  return (ghi || care || docs.find((d) => d.extraction_status === "extracted" || d.status === "extracted"))?.id;
}

async function main() {
  const failures = [];
  const docId = await pickGhiId();
  if (!docId) {
    console.error("No extracted GMC document found");
    process.exit(2);
  }

  const browser = await chromium.launch(chromiumLaunchOptions());
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  await page.goto(`${FE}/workspace?doc=${docId}`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForTimeout(1800);

  const body0 = await page.locator("body").innerText();
  if (/Select a document from the dropdown/i.test(body0)) {
    failures.push("cold-start empty select");
  }
  const selected = await page.locator("[data-testid=workspace-doc-select]").inputValue().catch(() => "");
  const selectedLabel = await page
    .locator("[data-testid=workspace-doc-select] option:checked")
    .textContent()
    .catch(() => "");
  console.log("SELECTED", selectedLabel || selected);
  if (/GPA|Net Catalyst|liberty/i.test(selectedLabel || "")) {
    failures.push(`defaulted to sparse GPA doc: ${selectedLabel}`);
  }
  if (!/Insurer & TPA/i.test(body0)) {
    failures.push("missing Insurer & TPA tab on load");
  }
  if (!/Care Health|Insurer/i.test(body0)) {
    failures.push("Insurer & TPA identity not visible on load");
  }
  if (/\bActivity\b/i.test(body0) || /llm_error/i.test(body0)) {
    failures.push("Activity / llm_error clutter visible");
  }
  if (/Knowledge Graph/i.test(body0)) {
    failures.push("Knowledge Graph still in nav/UI");
  }

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  if (overflow.scrollWidth > overflow.clientWidth + 2) {
    failures.push(
      `page horizontal overflow: scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`,
    );
  } else {
    console.log("OK no-page-overflow", `${overflow.clientWidth}px`);
  }

  await page.screenshot({ path: join(OUT, "assign-landing.png"), fullPage: true });

  for (const tab of TABS) {
    try {
      await page.getByRole("tab", { name: tab.name }).click({ timeout: 5000 });
      await page.waitForTimeout(600);
      const text = await page.locator("body").innerText();
      await page.screenshot({ path: join(OUT, `assign-${tab.slug}.png`), fullPage: true });
      if (!tab.expect.test(text)) {
        failures.push(`tab ${tab.slug}: expected content missing`);
      } else {
        console.log("OK", tab.slug);
      }
    } catch (e) {
      failures.push(`tab ${tab.slug}: ${e.message}`);
    }
  }

  await browser.close();

  const report = [
    "# Assignment UI loop",
    "",
    `doc=${docId}`,
    `selected=${selectedLabel}`,
    "",
    failures.length ? "## Failures" : "## ALL PASS",
    ...failures.map((f, i) => `${i + 1}. ${f}`),
    "",
  ].join("\n");
  writeFileSync(join(OUT, "ASSIGNMENT_UI_LOOP.md"), report);
  console.log(report);
  process.exit(failures.length ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(2);
});
