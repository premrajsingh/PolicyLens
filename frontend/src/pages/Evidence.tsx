import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileSearch, Loader2 } from "lucide-react";
import { api, apiUrl } from "../lib/api";
import { displayFilename, fieldLabel, sectionLabel } from "../lib/labels";
import { useDocumentSelection } from "../hooks/useDocumentSelection";
import StatusBadge from "../components/StatusBadge";
import type { EvidenceField } from "../types";

interface EvidenceContentProps {
  documentId?: string;
  embedded?: boolean;
}

export default function Evidence({ documentId: propId, embedded = false }: EvidenceContentProps) {
  const documents = useQuery({
    queryKey: ["documents"],
    queryFn: () => api.listDocuments(),
    enabled: !embedded,
  });
  const { selectedId, setSelectedId, selectable } = useDocumentSelection(
    embedded ? undefined : documents.data?.documents,
  );
  const documentId = propId ?? selectedId;

  const evidence = useQuery({
    queryKey: ["evidence", documentId],
    queryFn: () => api.getEvidence(documentId),
    enabled: !!documentId,
    retry: false,
  });

  const grouped = useMemo(() => groupEvidence(evidence.data?.fields ?? []), [evidence.data?.fields]);

  const content = (
    <>
      {!embedded && (
        <header className="mb-6">
          <h1 className="page-title">Evidence</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Source quotes and page citations backing each extracted field
          </p>
        </header>
      )}

      {!embedded && (
        <div className="mb-6">
          <select
            aria-label="Select policy for evidence"
            className="select max-w-md"
            value={documentId}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {selectable.length === 0 && <option value="">No documents yet…</option>}
            {selectable.map((d) => (
              <option key={d.id} value={d.id}>
                {displayFilename(d.original_filename || d.filename)}
              </option>
            ))}
          </select>
        </div>
      )}

      {!documentId ? (
        <div className="empty-state">
          <FileSearch className="mb-3 h-8 w-8 text-ink-faint" />
          <p className="text-sm text-ink-muted">Upload a policy in Policies to view evidence.</p>
        </div>
      ) : evidence.isLoading ? (
        <div className="flex items-center py-12 text-ink-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Loading evidence…
        </div>
      ) : evidence.isError ? (
        <div className="empty-state">
          <p className="text-sm text-ink-muted">
            No evidence available. Extract the policy first.
          </p>
        </div>
      ) : !evidence.data?.fields.length ? (
        <div className="empty-state">
          <p className="text-sm text-ink-muted">No evidence records found for this document.</p>
        </div>
      ) : (
        <div className="space-y-8">
          {grouped.map((group) => (
            <section key={group.key}>
              <h3 className="mb-3 text-sm font-semibold text-ink">{group.label}</h3>
              <div className="space-y-3">
                {group.fields.map((field) => (
                  <EvidenceCard key={field.field_path} field={field} documentId={documentId} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );

  if (embedded) return content;
  return <div className="app-shell">{content}</div>;
}

export { Evidence as EvidenceContent };

function EvidenceCard({ field, documentId }: { field: EvidenceField; documentId: string }) {
  const hasValue = field.value !== undefined && field.value !== null && field.value !== "";
  const quotes = (field.evidence ?? []).filter((ev) => ev.quote);

  // Prefer fields with evidence/value first visually via opacity for empties
  if (!hasValue && quotes.length === 0) return null;

  return (
    <article className="card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink">{fieldLabel(field.field_path)}</span>
        {field.status && <StatusBadge status={field.status} />}
        {field.confidence != null && field.confidence > 0 && (
          <span className="text-xs text-ink-faint">
            {Math.round(field.confidence * 100)}% confidence
          </span>
        )}
      </div>
      {hasValue && (
        <div className="mb-3 text-sm text-ink">
          <span className="font-medium text-ink-muted">Value: </span>
          {typeof field.value === "object" ? JSON.stringify(field.value) : String(field.value)}
        </div>
      )}
      {quotes.length > 0 ? (
        <ul className="space-y-2">
          {quotes.map((ev, i) => (
            <li
              key={i}
              className="rounded-lg border border-border bg-surface-muted/40 p-3 text-sm"
            >
              <div className="mb-1 flex flex-wrap gap-2 text-xs text-ink-faint">
                <a className="text-brand-700 underline" target="_blank" rel="noreferrer" href={`${apiUrl(`/documents/${documentId}/file`)}#page=${ev.page_number}`}>Page {ev.page_number} · Open source</a>
                {ev.section && <span>· {ev.section}</span>}
              </div>
              <blockquote className="border-l-2 border-brand-700/40 pl-3 italic text-ink-muted">
                "{ev.quote}"
              </blockquote>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-ink-faint">No source quotes attached.</p>
      )}
    </article>
  );
}

function groupEvidence(fields: EvidenceField[]) {
  const order = [
    "identity",
    "current_policy",
    "previous_policy",
    "policy_structure",
    "demographics",
    "hospitalization",
    "maternity",
    "waiting_periods",
    "other_benefits",
    "infertility_and_ambulance",
    "buffer_and_waivers",
    "other",
  ];
  const buckets = new Map<string, EvidenceField[]>();
  for (const field of fields) {
    if (!field.evidence?.length && field.value == null) continue;
    const root = field.field_path.includes(".")
      ? field.field_path.split(".")[0]
      : ["insurer", "tpa", "claims_administrator", "policy_type", "policy_number", "group_company_name"].includes(field.field_path)
        ? "identity"
        : "other";
    const key = order.includes(root) ? root : "other";
    if (!buckets.has(key)) buckets.set(key, []);
    buckets.get(key)!.push(field);
  }
  return order
    .filter((k) => buckets.has(k) && buckets.get(k)!.length > 0)
    .map((key) => ({
      key,
      label: key === "identity" ? "Identity" : sectionLabel(key),
      fields: buckets.get(key)!,
    }));
}
