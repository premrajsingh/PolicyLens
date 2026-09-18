import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { GitCompare, Loader2 } from "lucide-react";
import { api } from "../lib/api";
import { displayFilename, fieldLabel } from "../lib/labels";
import StatusBadge from "../components/StatusBadge";
import type { CompareDifference } from "../types";

export default function Compare() {
  const [firstId, setFirstId] = useState("");
  const [secondId, setSecondId] = useState("");

  const documents = useQuery({ queryKey: ["documents"], queryFn: () => api.listDocuments() });

  const extractedDocs = useMemo(
    () =>
      (documents.data?.documents ?? []).filter((d) => {
        if (d.status === "duplicate") return false;
        const statuses = [d.extraction_status, d.status];
        return statuses.some((s) => s === "extracted" || s === "partial");
      }),
    [documents.data?.documents],
  );

  useEffect(() => {
    if (extractedDocs.length < 2) return;
    if (!firstId) setFirstId(extractedDocs[0].id);
    if (!secondId) {
      const second = extractedDocs.find((d) => d.id !== (firstId || extractedDocs[0].id));
      if (second) setSecondId(second.id);
    }
  }, [extractedDocs, firstId, secondId]);

  const compareMutation = useMutation({
    mutationFn: () => api.compare(firstId, secondId),
  });

  const canCompare = firstId && secondId && firstId !== secondId;

  return (
    <div className="app-shell space-y-6">
      <header>
        <h1 className="page-title">Compare policies</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Side-by-side diff of extracted fields between two policies
        </p>
      </header>

      <div className="card p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-ink-muted">First policy</label>
            <select aria-label="First policy" className="select" value={firstId} onChange={(e) => { setFirstId(e.target.value); compareMutation.reset(); }}>
              <option value="">Select document…</option>
              {extractedDocs.map((d) => (
                <option key={d.id} value={d.id}>
                  {displayFilename(d.original_filename || d.filename)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-ink-muted">Second policy</label>
            <select
              aria-label="Second policy"
              className="select"
              value={secondId}
              onChange={(e) => { setSecondId(e.target.value); compareMutation.reset(); }}
            >
              <option value="">Select document…</option>
              {extractedDocs.map((d) => (
                <option key={d.id} value={d.id}>
                  {displayFilename(d.original_filename || d.filename)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <button
          type="button"
          className="btn-primary mt-4"
          disabled={!canCompare || compareMutation.isPending}
          onClick={() => compareMutation.mutate()}
        >
          {compareMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <GitCompare className="h-4 w-4" />
          )}
          Compare policies
        </button>

        {firstId && secondId && firstId === secondId && (
          <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
            Select two different documents to compare.
          </p>
        )}

        {extractedDocs.length < 2 && documents.data && (
          <p className="mt-2 text-xs text-ink-faint">
            At least two extracted policies are required for comparison.
          </p>
        )}
      </div>

      {compareMutation.isError && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
          {(compareMutation.error as Error).message}
        </div>
      )}

      {compareMutation.data && (
        <CompareResults
          data={compareMutation.data}
          firstName={
            displayFilename(
              extractedDocs.find((d) => d.id === firstId)?.original_filename ||
                extractedDocs.find((d) => d.id === firstId)?.filename,
            ) || "Policy A"
          }
          secondName={
            displayFilename(
              extractedDocs.find((d) => d.id === secondId)?.original_filename ||
                extractedDocs.find((d) => d.id === secondId)?.filename,
            ) || "Policy B"
          }
        />
      )}

      {!compareMutation.data && !compareMutation.isPending && (
        <div className="empty-state">
          <GitCompare className="mb-3 h-8 w-8 text-ink-faint" />
          <p className="text-sm text-ink-muted">
            {extractedDocs.length >= 2
              ? "Two policies are selected — click Compare policies to view differences."
              : "Extract at least two policies, then compare field-level differences here."}
          </p>
        </div>
      )}
    </div>
  );
}

function CompareResults({
  data,
  firstName,
  secondName,
}: {
  data: {
    difference_count: number;
    differences: CompareDifference[];
    graph_compare?: Record<string, unknown>;
  };
  firstName: string;
  secondName: string;
}) {
  const graphSummary = summarizeGraphCompare(data.graph_compare);

  return (
    <div className="space-y-4">
      <div className="card px-5 py-4">
        <div className="text-sm text-ink-muted">
          Found{" "}
          <span className="font-semibold text-ink">{data.difference_count}</span> field
          {data.difference_count === 1 ? "" : "s"} with differences
        </div>
      </div>

      {data.differences.length === 0 ? (
        <div className="empty-state">
          <p className="text-sm text-ink-muted">No field differences detected.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.differences.map((diff) => (
            <div key={diff.field_path} className="card overflow-hidden">
              <div className="border-b border-border bg-surface-muted/40 px-4 py-2">
                <span className="text-sm font-medium text-ink">{fieldLabel(diff.field_path)}</span>
              </div>
              <div className="grid divide-y divide-border md:grid-cols-2 md:divide-x md:divide-y-0">
                <DiffColumn title={firstName} field={diff.first} />
                <DiffColumn title={secondName} field={diff.second} />
              </div>
            </div>
          ))}
        </div>
      )}

      {graphSummary && (
        <div className="card p-5">
          <h3 className="mb-2 text-sm font-semibold text-ink">Graph comparison</h3>
          <p className="text-sm text-ink-muted">{graphSummary}</p>
        </div>
      )}
    </div>
  );
}

function summarizeGraphCompare(graph?: Record<string, unknown>): string | null {
  if (!graph || Object.keys(graph).length === 0) return null;
  const parts: string[] = [];
  for (const [k, v] of Object.entries(graph)) {
    if (typeof v === "number") parts.push(`${k.replace(/_/g, " ")}: ${v}`);
    else if (typeof v === "string") parts.push(`${k.replace(/_/g, " ")}: ${v}`);
    else if (Array.isArray(v)) parts.push(`${k.replace(/_/g, " ")}: ${v.length} items`);
  }
  return parts.length ? parts.join(" · ") : null;
}

function DiffColumn({
  title,
  field,
}: {
  title: string;
  field?: Record<string, unknown>;
}) {
  const evidence = Array.isArray(field?.evidence) ? (field.evidence as Array<Record<string, unknown>>) : [];
  const quote = evidence[0]?.quote;

  return (
    <div className="p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
        {title}
      </div>
      {!field ? (
        <p className="text-sm italic text-ink-faint">Not present</p>
      ) : (
        <>
          <div className="text-sm text-ink">
            <span className="text-ink-muted">Value: </span>
            {formatCompareValue(field.value)}
          </div>
          {field.status != null && (
            <div className="mt-2">
              <StatusBadge status={String(field.status)} />
            </div>
          )}
          {Array.isArray(field.conditions) && <p className="mt-2 text-xs leading-6 text-ink-muted">{field.conditions.join("; ")}</p>}
          {typeof quote === "string" && quote && (
            <blockquote className="mt-3 border-l-2 border-brand-700/40 pl-3 text-xs italic text-ink-muted">
              “{quote.slice(0, 220)}{quote.length > 220 ? "…" : ""}”
            </blockquote>
          )}
        </>
      )}
    </div>
  );
}

function formatCompareValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}
