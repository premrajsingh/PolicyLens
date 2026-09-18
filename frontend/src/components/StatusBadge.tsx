import type { ProviderStatus } from "../types";

type BadgeVariant = "default" | "ocr" | "pinecone" | "neo4j" | "extraction" | "provider";

const statusStyles: Record<string, string> = {
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  processed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  extracted: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  complete: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  synced: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  indexed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  local_indexed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  local_synced: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  pending: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  uploaded: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
  processing: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  running: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  degraded: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  error: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  disabled: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  skipped: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  not_applicable: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  unknown: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  covered: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
  not_covered: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
  waived_off: "bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-300",
  applied: "bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300",
  duplicate: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
  partial: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  partially_covered: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
  conflict: "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
};

const variantPrefix: Record<BadgeVariant, string> = {
  default: "",
  ocr: "OCR · ",
  pinecone: "Vector · ",
  neo4j: "Graph · ",
  extraction: "Extract · ",
  provider: "",
};

interface StatusBadgeProps {
  status: string;
  variant?: BadgeVariant;
  className?: string;
}

const DISPLAY_LABELS: Record<string, string> = {
  unknown: "Unknown",
  not_applicable: "Not applicable",
  covered: "Covered",
  not_covered: "Not covered",
  waived_off: "Waived",
  partially_covered: "Partial",
  local_indexed: "Indexed (local)",
  local_synced: "Synced (local)",
};

export default function StatusBadge({ status, variant = "default", className = "" }: StatusBadgeProps) {
  const normalized = (status || "unknown").toLowerCase().replace(/\s+/g, "_");
  const style = statusStyles[normalized] ?? statusStyles.unknown;
  const pretty =
    DISPLAY_LABELS[normalized] ??
    status.replace(/_/g, " ");
  const label = `${variantPrefix[variant]}${pretty}`;

  return (
    <span className={`badge capitalize ${style} ${className}`}>{label}</span>
  );
}

export function ProviderStatusBadge({ status }: { status: ProviderStatus }) {
  return <StatusBadge status={status} variant="provider" />;
}
