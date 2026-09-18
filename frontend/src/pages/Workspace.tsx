import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { AlertCircle, ArrowUpRight, Download, FileText, Loader2, RefreshCw, ShieldCheck, ChevronDown, Search } from "lucide-react";
import { Link } from "react-router-dom";
import { api, apiUrl, formatPercent } from "../lib/api";
import { displayFilename, fieldLabel, sectionLabel } from "../lib/labels";
import { useDocumentSelection } from "../hooks/useDocumentSelection";
import type { ExtractionPayload, EvidenceItem } from "../types";
import JsonViewer from "../components/JsonViewer";
import StatusBadge from "../components/StatusBadge";
import EvidenceContent from "./Evidence";

const TAB_DEFS = [
  {
    id: "identity",
    label: "Insurer & TPA",
    cue: "Automatically identify the insurance company / insurer and existing TPA from the policy.",
    kind: "identity" as const,
  },
  {
    id: "policy_details",
    label: "Policy details",
    cue: "Current schedule and explicitly stated previous-year details are kept separate.",
    kind: "sections" as const,
    sections: ["current_policy", "previous_policy"],
  },
  {
    id: "policy_structure",
    label: "Policy Structure",
    cue: "Family structure and multiple Sum Insured tiers.",
    kind: "sections" as const,
    sections: ["policy_structure"],
  },
  {
    id: "demographics",
    label: "Demographics",
    cue: "Employees, spouses, children, parents / parents-in-law, and total lives covered.",
    kind: "sections" as const,
    sections: ["demographics"],
  },
  {
    id: "hospitalization",
    label: "Room & Hospitalization",
    cue: "Covered / Not Covered / Waived — room rent, ICU, pre- and post-hospitalization days.",
    kind: "sections" as const,
    sections: ["hospitalization"],
  },
  {
    id: "maternity",
    label: "Maternity",
    cue: "9-month waiting, baby day-one, vaccination, and metro / non-metro delivery limits.",
    kind: "sections" as const,
    sections: ["maternity"],
  },
  {
    id: "waiting_periods",
    label: "Waiting Periods",
    cue: "Applied / Waived Off / Not Covered for 30-day, 1st/2nd year, and PED waiting periods.",
    kind: "sections" as const,
    sections: ["waiting_periods"],
  },
  {
    id: "other_benefits",
    label: "Other Benefits",
    cue: "Daycare, OPD, AYUSH, organ donor, and related benefit limits.",
    kind: "sections" as const,
    sections: ["other_benefits"],
  },
  {
    id: "infertility_and_ambulance",
    label: "Infertility & Ambulance",
    cue: "Infertility, surrogacy, ambulance, and air ambulance coverage.",
    kind: "sections" as const,
    sections: ["infertility_and_ambulance"],
  },
  {
    id: "buffer_and_waivers",
    label: "Buffer & Waivers",
    cue: "Corporate buffer, disease-wise capping, and waiver conditions.",
    kind: "sections" as const,
    sections: ["buffer_and_waivers"],
  },
  {
    id: "evidence",
    label: "Evidence",
    cue: "Source quotes and page citations for each extracted field.",
    kind: "evidence" as const,
  },
  {
    id: "qms_json",
    label: "QMS JSON",
    cue: "Machine-readable structured JSON mapped to QMS fields.",
    kind: "json" as const,
  },
] as const;

type Tab = (typeof TAB_DEFS)[number]["id"];


export default function Workspace() {
  const [activeTab, setActiveTab] = useState<Tab>("identity");
  const queryClient = useQueryClient();
  const documents = useQuery({queryKey: ["documents"], queryFn: () => api.listDocuments(), refetchInterval: 5000});
  const {selectedId, setSelectedId, selectable} = useDocumentSelection(documents.data?.documents);
  const selectedDoc = selectable.find(d => d.id === selectedId);
  const status = useQuery({queryKey: ["document-status", selectedId], queryFn: () => api.documentStatus(selectedId), enabled: !!selectedId, refetchInterval: 3000});
  const docStatus = status.data?.document.status ?? selectedDoc?.status;
  const busy = ["queued", "processing", "uploaded"].includes(docStatus ?? "");
  const extraction = useQuery({queryKey: ["extraction", selectedId], queryFn: () => api.getExtraction(selectedId), enabled: !!selectedId, retry: false, refetchInterval: busy ? 3000 : false});
  useEffect(() => {
    queryClient.invalidateQueries({queryKey: ["extraction", selectedId]});
    queryClient.invalidateQueries({queryKey: ["evidence", selectedId]});
  }, [status.data?.document.updated_at, selectedId, queryClient]);
  const retry = useMutation({mutationFn: (id: string) => api.retryDocument(id), onSuccess: () => {queryClient.invalidateQueries({queryKey: ["documents"]}); queryClient.invalidateQueries({queryKey: ["document-status"]});}});
  const payload = extraction.data as ExtractionPayload | undefined;
  const metadata = (payload?.extraction_metadata ?? {}) as Record<string, unknown>;
  const validation = (payload?.validation ?? {}) as Record<string, unknown>;
  const policyType = (payload?.policy_type as Record<string, unknown> | undefined)?.value;
  const def = TAB_DEFS.find(t => t.id === activeTab)!;
  const warnings = Array.isArray(validation.extraction_warnings) ? validation.extraction_warnings as string[] : [];
  return <div className="app-shell space-y-6" data-testid="workspace-shell">
    <header className="flex flex-wrap items-end justify-between gap-4"><div><div className="eyebrow">DOCUMENT REVIEW</div><h1 className="page-title mt-2">Policy extraction</h1><p className="mt-2 text-sm text-ink-muted">Every detail, its conditions, and the evidence behind it.</p></div><div className="flex gap-2">{selectedId && <a href={apiUrl(`/documents/${selectedId}/file`)} target="_blank" rel="noreferrer" className="btn-secondary"><FileText className="h-4 w-4"/>Source PDF<ArrowUpRight className="h-3.5 w-3.5"/></a>}{payload && <a href={apiUrl(`/policies/${selectedId}/download`)} className="btn-primary" download><Download className="h-4 w-4"/>Export JSON</a>}</div></header>
    <div className="card flex flex-wrap items-center justify-between gap-4 px-5 py-4"><div className="min-w-0 flex-1"><label htmlFor="policy-select" className="mb-1.5 block text-[11px] font-medium text-ink-muted">SELECTED POLICY</label><select id="policy-select" aria-label="Selected policy" className="select max-w-xl" value={selectedId} onChange={e => setSelectedId(e.target.value)} data-testid="workspace-doc-select">{!selectable.length && <option value="">No documents yet</option>}{selectable.map(d => <option value={d.id} key={d.id}>{displayFilename(d.original_filename || d.filename)}</option>)}</select></div>{selectedId && <div className="flex items-center gap-3"><StatusBadge status={docStatus ?? "unknown"}/><button className="btn-secondary text-xs" onClick={() => retry.mutate(selectedId)} disabled={busy || retry.isPending}>{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin"/> : <RefreshCw className="h-3.5 w-3.5"/>}{busy ? "Processing…" : payload ? "Re-extract" : "Extract policy"}</button></div>}</div>
    {documents.isError && <Notice>Unable to load documents. Check the API connection.</Notice>}
    {(retry.isError || docStatus === "error") && <Notice>{retry.error?.message || status.data?.document.error_message || "Processing failed. Check settings and retry."}</Notice>}
    {selectedId && extraction.isError && !busy && (
      <Notice>
        {extraction.error instanceof Error
          ? extraction.error.message
          : "Unable to load extraction. Check the API connection and retry."}
      </Notice>
    )}
    {busy && <div role="status" className="flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50 p-4 text-sm text-brand-900 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-100"><Loader2 className="h-4 w-4 animate-spin"/><span>Reading and checking your policy. {status.data?.latest_job?.stage === "structured_extraction" ? "Extracting policy fields; provider rate limits may take a few minutes." : "You can leave this page and return when processing finishes."}</span></div>}
    {policyType === "gpa" && <Notice>This source is a Group Personal Accident policy. GMC benefit sections are marked not applicable based on the document content.</Notice>}
    {metadata.completion_status === "partial" && <Notice>Some provider requests failed. This extraction is incomplete; retry before using it in your QMS.</Notice>}
    {metadata.completion_status === "offline" && <Notice>Offline demonstration mode uses limited rules. Configure an AI provider in Settings for full extraction.</Notice>}
    {!selectedId ? <div className="empty-state"><FileText className="mb-4 h-8 w-8 text-ink-faint"/><h2 className="font-semibold">Add a policy to begin</h2><p className="mt-2 text-sm text-ink-muted">Upload a PDF and the extraction starts automatically.</p><Link className="btn-primary mt-5" to="/knowledge-base">Upload policy</Link></div> : extraction.isError && !busy ? <div className="empty-state"><AlertCircle className="mb-4 h-8 w-8 text-ink-faint"/><p className="font-medium">Extraction could not be loaded</p><p className="mt-2 text-sm text-ink-muted">Use Extract policy above to retry, or check Settings / API health.</p></div> : !payload ? <div className="empty-state"><Search className="mb-4 h-8 w-8 text-ink-faint"/><p className="font-medium">{busy ? "Your extraction is on its way" : "No extraction available yet"}</p><p className="mt-2 text-sm text-ink-muted">{busy ? "Results will appear here automatically." : "Use Extract policy above to start."}</p></div> : <>
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[{label:"Fields extracted",value:validation.fields_found ?? 0},{label:"Unknown fields",value:validation.fields_missing ?? 0},{label:"Review flags",value:validation.fields_requiring_review ?? 0},{label:"Evidence coverage",value:formatPercent(Number(validation.evidence_coverage ?? 0))}].map(item=><div className="card px-5 py-4" key={item.label}><div className="text-[11px] text-ink-muted">{item.label}</div><div className="mt-2 text-2xl font-semibold tabular-nums">{String(item.value)}</div></div>)}</div>
    {warnings.length > 0 && <details className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"><summary className="cursor-pointer font-medium">{warnings.length} validation notes</summary><ul className="mt-3 list-disc space-y-2 pl-4">{warnings.map((w,i)=><li key={i}>{w}</li>)}</ul></details>}
    <div className="card grid min-w-0 overflow-hidden lg:grid-cols-[210px_minmax(0,1fr)]" data-testid="workspace-main-card">
      <nav className="flex min-h-0 flex-col border-b border-border bg-surface/70 p-5 lg:border-b-0 lg:border-r sm:p-6" aria-label="Policy sections">
        <div className="mb-5 border-b border-border pb-5">
          <p className="eyebrow">POLICY SECTIONS</p>
          <p className="mt-2 text-xs leading-5 text-ink-muted">Jump to an assignment group</p>
        </div>
        <div role="tablist" aria-orientation="vertical" className="hidden space-y-1 lg:block">
          {TAB_DEFS.map((tab,index)=>(
            <button key={tab.id} role="tab" aria-selected={activeTab === tab.id} aria-controls="extraction-panel" className="section-nav" onClick={()=>setActiveTab(tab.id)}>
              <span className="flex items-center gap-2.5"><span className="w-4 text-[10px] opacity-50">{String(index+1).padStart(2,"0")}</span>{tab.label}</span>
            </button>
          ))}
        </div>
        <select className="select lg:hidden" aria-label="Policy section" value={activeTab} onChange={e=>setActiveTab(e.target.value as Tab)}>
          {TAB_DEFS.map(t=><option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
        <div className="mt-auto hidden pt-6 lg:block">
          <div className="rounded-lg bg-surface-muted/70 p-3">
            <ShieldCheck className="h-4 w-4 text-brand-700"/>
            <p className="mt-2 text-[11px] leading-5 text-ink-muted">Expand a field to inspect conditions and source quotes.</p>
          </div>
        </div>
      </nav>
      <section id="extraction-panel" role="tabpanel" aria-label={def.label} className="min-w-0 p-5 sm:p-6">
        <div className="mb-5 border-b border-border pb-5">
          <h2 className="text-lg font-semibold leading-none">{def.label}</h2>
          <p className="mt-2 text-xs leading-5 text-ink-muted">{def.cue}</p>
        </div>
        {def.kind === "identity" ? <FieldList data={Object.fromEntries(["insurer","tpa","claims_administrator","policy_type","policy_number","group_company_name"].map(k=>[k,payload[k]]))} documentId={selectedId}/> : def.kind === "sections" ? <div className="space-y-8">{def.sections.map(section=><div key={section}><h3 className="mb-4 text-sm font-semibold">{sectionLabel(section)}</h3>{section === "previous_policy" && <p className="mb-4 text-xs leading-6 text-ink-muted">Historical details are populated only when the source explicitly identifies a previous policy. The age of the document does not establish this.</p>}<FieldList key={section} data={payload[section]} prefix={section} documentId={selectedId}/></div>)}</div> : def.kind === "evidence" ? <EvidenceContent documentId={selectedId} embedded/> : <JsonViewer data={payload}/>}
      </section>
    </div>
    <p className="flex items-center gap-2 text-[11px] text-ink-muted"><ShieldCheck className="h-3.5 w-3.5"/>Source checks establish citation support. Model confidence is not a measured accuracy score.</p>
    </>}
  </div>;
}

interface Field { value?: unknown; normalized_value?: unknown; status?: string; confidence?: number; conditions?: string[]; warnings?: string[]; conflicts?: string[]; evidence?: EvidenceItem[]; }
function FieldList({data, prefix="", documentId}:{data:unknown; prefix?:string; documentId:string}) {
  const [showUnknown,setShowUnknown]=useState(true);
  const rows=useMemo(()=>Object.entries((data ?? {}) as Record<string,Field>).filter(([,field])=>field && typeof field === "object" && "status" in field),[data]);
  const unknown=rows.filter(([,field])=>field.status === "unknown" && field.value == null).length;
  return <div><div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-muted"><span>{rows.length-unknown} resolved · {unknown} unknown</span>{unknown>0 && <label className="flex cursor-pointer items-center gap-2"><input type="checkbox" className="accent-teal-700" checked={showUnknown} onChange={e=>setShowUnknown(e.target.checked)}/>Show unknown fields</label>}</div><div className="divide-y divide-border rounded-xl border border-border">{rows.filter(([,f])=>showUnknown || f.status!=="unknown" || f.value!=null).map(([key,field])=><details key={key} className="group px-4 py-4 open:bg-surface-muted/30 sm:px-5"><summary className="flex cursor-pointer list-none items-start gap-3 [&::-webkit-details-marker]:hidden"><div className="min-w-0 flex-1"><div className="text-xs font-medium text-ink-muted">{fieldLabel(prefix ? `${prefix}.${key}` : key)}</div><div className="mt-1.5 break-words text-sm font-medium leading-6">{formatValue(field.value ?? field.normalized_value)}</div></div><div className="flex shrink-0 items-center gap-2 pt-0.5"><StatusBadge status={field.status || "unknown"}/><ChevronDown className="h-3.5 w-3.5 text-ink-faint transition-transform group-open:rotate-180"/></div></summary><div className="mt-4 space-y-4 border-t border-border pt-4">{field.conditions?.length ? <div><h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">Conditions and limits</h4><ul className="space-y-2 text-xs leading-6 text-ink-muted">{field.conditions.map((x,i)=><li key={i} className="field-detail">{x}</li>)}</ul></div> : null}{field.conflicts?.map((x,i)=><p key={i} className="text-xs text-amber-700">{x}</p>)}{field.evidence?.length ? <div className="space-y-3">{field.evidence.map((ev,i)=><div key={i} className="rounded-lg border border-border bg-surface-raised p-3"><a className="inline-flex items-center gap-1 text-[11px] font-semibold text-brand-700" target="_blank" rel="noreferrer" href={`${apiUrl(`/documents/${documentId}/file`)}#page=${ev.page_number}`}>Source · page {ev.page_number}<ArrowUpRight className="h-3 w-3"/></a><blockquote className="mt-2 whitespace-pre-wrap break-words text-xs leading-6 text-ink-muted">{ev.quote}</blockquote></div>)}</div> : <p className="text-xs text-ink-muted">No verified source evidence is available for this field.</p>}{field.warnings?.length ? <p className="text-xs text-amber-700 dark:text-amber-300">Review: {field.warnings.join(", ").replace(/_/g," ")}</p> : null}{Number(field.confidence)>0 && <p className="text-[11px] text-ink-muted">Model confidence {formatPercent(Number(field.confidence))} · not an accuracy score</p>}</div></details>)}</div></div>;
}
function formatValue(value: unknown): string {
  if (value == null || value === "") return "Not established";
  if (typeof value === "number") return new Intl.NumberFormat("en-IN").format(value);
  if (Array.isArray(value)) return value.map(formatValue).join(" · ");
  if (typeof value === "object") return Object.entries(value as Record<string,unknown>).map(([k,v])=>`${k.replace(/_/g," ")}: ${formatValue(v)}`).join("; ");
  return String(value).replace(/_/g," ");
}
function Notice({children}:{children:React.ReactNode}) {return <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-100"><AlertCircle className="mt-1 h-4 w-4 shrink-0"/><div>{children}</div></div>;}
