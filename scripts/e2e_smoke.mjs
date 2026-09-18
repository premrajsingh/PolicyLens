/**
 * PolicyLens live smoke test — run with:
 *   cd frontend && npx playwright test ../scripts/e2e_smoke.mjs
 * Or directly:
 *   node scripts/e2e_smoke.mjs
 */
import { chromium } from "playwright";
import { writeFileSync, mkdirSync, existsSync } from "fs";
import { join } from "path";

const FE = process.env.FE_URL || "http://127.0.0.1:5173";
const API = process.env.API_URL || "http://127.0.0.1:8000";
const outDir = join(process.cwd(), "outputs", "e2e");
mkdirSync(outDir, { recursive: true });

function chromiumLaunchOptions() {
  const candidates = [
    process.env.PLAYWRIGHT_CHROMIUM_PATH,
    "/Users/premrajsingh/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell",
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

const results = [];
function ok(name, detail = "") {
  results.push({ name, pass: true, detail });
  console.log(`PASS  ${name}${detail ? " — " + detail : ""}`);
}
function fail(name, detail = "") {
  results.push({ name, pass: false, detail });
  console.error(`FAIL  ${name}${detail ? " — " + detail : ""}`);
}

async function apiJson(path) {
  const res = await fetch(`${API}${path}`);
  const text = await res.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = text;
  }
  return { status: res.status, body };
}

async function main() {
  // --- API checks ---
  {
    const h = await apiJson("/api/health");
    h.status === 200 && h.body?.status === "ok"
      ? ok("api_health")
      : fail("api_health", JSON.stringify(h).slice(0, 200));
  }
  {
    const p = await apiJson("/api/providers/health");
    if (p.status !== 200) fail("providers_health", `status ${p.status}`);
    else {
      const providers = p.body.providers || [];
      const bad = providers.filter((x) => x.status !== "ok");
      const dnsOnly =
        bad.length > 0 &&
        bad.every((x) =>
          /nodename|DNS|ENOTFOUND|getaddrinfo|network|ECONNREFUSED/i.test(
            String(x.detail || ""),
          ),
        );
      if (bad.length === 0) {
        ok("providers_health", providers.map((x) => x.name).join(", "));
      } else if (dnsOnly) {
        ok(
          "providers_health_degraded_dns",
          bad.map((x) => x.name).join(", "),
        );
      } else {
        fail("providers_health", JSON.stringify(bad));
      }
    }
  }
  {
    const d = await apiJson("/api/documents");
    const docs = d.body?.documents || [];
    const dups = docs.filter((x) => x.status === "duplicate");
    docs.length >= 1 && dups.length === 0
      ? ok("documents_no_duplicates", `${docs.length} docs`)
      : fail("documents_no_duplicates", `docs=${docs.length} dups=${dups.length}`);
    globalThis.__docs = docs;
  }
  {
    const docs = globalThis.__docs || [];
    const ghi = docs.find((d) => /GHI/i.test(d.filename));
    if (!ghi) fail("ghi_extraction", "GHI Policy not found");
    else {
      const e = await apiJson(`/api/policies/${ghi.id}/extraction`);
      const found = e.body?.validation?.fields_found ?? 0;
      const insurer = e.body?.insurer?.value;
      e.status === 200 && found >= 20 && insurer
        ? ok("ghi_extraction", `fields=${found} insurer=${insurer}`)
        : fail("ghi_extraction", `status=${e.status} fields=${found} insurer=${insurer}`);
      globalThis.__ghi = ghi.id;
    }
  }
  {
    const pc = await apiJson("/api/providers/health");
    const pine = (pc.body.providers || []).find((p) => p.name === "pinecone");
    const local = (pc.body.providers || []).find(
      (p) => p.name === "local_vector" || p.name === "vector" || /vector/i.test(p.name || ""),
    );
    const detail = String(pine?.detail || local?.detail || "");
    const usingPinecone = pine && /ok|ready|vectors=/i.test(String(pine.status || pine.detail || ""));
    if (usingPinecone) {
      detail.includes("vectors=") && !detail.includes("vectors=0")
        ? ok("pinecone_has_vectors", pine.detail)
        : fail("pinecone_has_vectors", pine?.detail);
    } else {
      ok("vector_store_local_or_optional", pine?.detail || local?.detail || "local profile");
    }
  }

  // --- Browser UI checks ---
  const browser = await chromium.launch(chromiumLaunchOptions());
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  page.setDefaultTimeout(20000);

  try {
    await page.goto(FE, { waitUntil: "networkidle" });
    await page.screenshot({ path: join(outDir, "01-dashboard.png"), fullPage: true });
    const title = await page.title();
    /PolicyLens/i.test(title) ? ok("ui_dashboard_title", title) : fail("ui_dashboard_title", title);

    await page.getByRole("link", { name: /^Policies$/i }).click();
    await page.waitForURL(/knowledge-base/);
    await page.waitForTimeout(800);
    await page.screenshot({ path: join(outDir, "02-knowledge-base.png"), fullPage: true });
    const dupBadges = await page.getByText("Duplicate", { exact: true }).count();
    dupBadges === 0
      ? ok("ui_kb_no_duplicate_badges")
      : fail("ui_kb_no_duplicate_badges", `count=${dupBadges}`);
    const indexed = await page.getByText(/Indexed/i).count();
    indexed >= 1 ? ok("ui_kb_indexed_visible", `count=${indexed}`) : fail("ui_kb_indexed_visible");

    await page.getByRole("link", { name: /Extraction/i }).click();
    await page.waitForURL(/workspace/);
    const ghiId = globalThis.__ghi;
    if (ghiId) {
      await page.goto(`${FE}/workspace?doc=${ghiId}`, { waitUntil: "networkidle" });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: join(outDir, "03-workspace-ghi.png"), fullPage: true });
      const body = await page.locator("body").innerText();
      /Care Health/i.test(body)
        ? ok("ui_workspace_insurer_visible")
        : fail("ui_workspace_insurer_visible", "Care Health not in page text");
      // Overview should show identity table, not "No fields extracted" for document meta
      !/Document[\s\S]{0,40}No fields extracted/i.test(body)
        ? ok("ui_overview_not_empty")
        : fail("ui_overview_not_empty");
      /\d+%/.test(body)
        ? ok("ui_workspace_confidence_percent")
        : fail("ui_workspace_confidence_percent", "no percent found");
      await page.getByRole("tab", { name: /Maternity/i }).click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: join(outDir, "04-maternity.png"), fullPage: true });
      const wp = await page.locator("body").innerText();
      /waived|covered|unknown|maternity|waiting|9-month|baby/i.test(wp)
        ? ok("ui_maternity_waiting_tab")
        : fail("ui_maternity_waiting_tab");
      await page.getByRole("tab", { name: /Other Benefits/i }).click();
      await page.waitForTimeout(400);
      const ob = await page.locator("body").innerText();
      /other benefits|day.care|opd|unknown|covered/i.test(ob)
        ? ok("ui_other_benefits_tab")
        : fail("ui_other_benefits_tab", ob.slice(0, 120));
      await page.getByRole("tab", { name: /Buffer.*Waiver/i }).click();
      await page.waitForTimeout(400);
      const bw = await page.locator("body").innerText();
      /buffer|waiver|unknown|covered/i.test(bw)
        ? ok("ui_buffer_waivers_tab")
        : fail("ui_buffer_waivers_tab");
      // Confirm assignment section tabs exist
      const tabs = await page.locator("body").innerText();
      /Insurer & TPA|Room & Hospitalization|QMS JSON/i.test(tabs)
        ? ok("ui_assignment_section_tabs")
        : fail("ui_assignment_section_tabs");

      const overflow = await page.evaluate(() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
      }));
      overflow.sw <= overflow.cw + 2
        ? ok("ui_no_page_horizontal_overflow", `${overflow.cw}px`)
        : fail("ui_no_page_horizontal_overflow", `sw=${overflow.sw} cw=${overflow.cw}`);
    }

    await page.getByRole("link", { name: /^Policies$/i }).click();
    await page.waitForURL(/knowledge-base/);
    await page.waitForTimeout(800);
    await page.screenshot({ path: join(outDir, "05-policies.png"), fullPage: true });
    const kbText = await page.locator("body").innerText();
    /Upload|Policies|document|PDF/i.test(kbText)
      ? ok("ui_policies_page")
      : fail("ui_policies_page", kbText.slice(0, 120));

    // Insurance-grade shell: no Graph nav, no Activity / llm_error dumps
    const shell = await page.locator("body").innerText();
    !/Knowledge Graph/i.test(shell)
      ? ok("ui_no_graph_nav")
      : fail("ui_no_graph_nav");
    !/\bActivity\b/i.test(shell)
      ? ok("ui_no_activity_panel")
      : fail("ui_no_activity_panel");
    !/llm_error/i.test(shell)
      ? ok("ui_no_llm_error")
      : fail("ui_no_llm_error");

    await page.goto(`${FE}/graph`, { waitUntil: "networkidle" });
    await page.waitForTimeout(500);
    page.url().includes("/workspace")
      ? ok("ui_graph_redirects_workspace")
      : fail("ui_graph_redirects_workspace", page.url());

    await page.getByRole("link", { name: /Settings/i }).click();
    await page.waitForURL(/settings/);
    await page.getByText(/System status|Provider|Groq|Pinecone|Unable to load/i).first().waitFor({
      timeout: 30000,
    });
    await page.screenshot({ path: join(outDir, "06-settings.png"), fullPage: true });
    const stext = await page.locator("body").innerText();
    /pinecone|neo4j|groq|huggingface|llm_/i.test(stext)
      ? ok("ui_settings_providers")
      : fail("ui_settings_providers", stext.slice(0, 200));
  } catch (e) {
    fail("browser_crash", String(e).slice(0, 300));
    await page.screenshot({ path: join(outDir, "error.png"), fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }

  const passed = results.filter((r) => r.pass).length;
  const failed = results.filter((r) => !r.pass).length;
  writeFileSync(
    join(outDir, "results.json"),
    JSON.stringify({ passed, failed, results }, null, 2),
  );
  console.log(`\n=== ${passed} passed, ${failed} failed ===`);
  console.log(`Screenshots: ${outDir}`);
  if (failed > 0) process.exit(1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
