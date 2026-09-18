import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Copy, Check } from "lucide-react";

interface JsonViewerProps {
  data: unknown;
  className?: string;
  maxHeight?: string;
}

export default function JsonViewer({
  data,
  className = "",
  maxHeight = "max-h-[600px]",
}: JsonViewerProps) {
  const [copied, setCopied] = useState(false);
  const json = useMemo(() => JSON.stringify(data, null, 2), [data]);

  const copy = async () => {
    await navigator.clipboard.writeText(json);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (data === null || data === undefined) {
    return (
      <div className="empty-state py-8">
        <p className="text-sm text-ink-muted">No JSON data available</p>
      </div>
    );
  }

  return (
    <div className={`card overflow-hidden ${className}`}>
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <span className="text-xs font-medium uppercase tracking-wide text-ink-faint">
          JSON payload
        </span>
        <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={copy}>
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <div className={`overflow-auto ${maxHeight}`}>
        <TreeNode name="root" value={data} depth={0} defaultOpen />
      </div>
    </div>
  );
}

function TreeNode({
  name,
  value,
  depth,
  defaultOpen = false,
}: {
  name: string;
  value: unknown;
  depth: number;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen && depth < 2);
  const indent = depth * 16;

  if (value === null || value === undefined) {
    return (
      <div className="font-mono text-xs leading-6" style={{ paddingLeft: indent }}>
        <span className="text-ink-muted">{name}: </span>
        <span className="text-ink-faint">null</span>
      </div>
    );
  }

  if (typeof value !== "object") {
    const color =
      typeof value === "string"
        ? "text-emerald-700 dark:text-emerald-400"
        : typeof value === "number"
          ? "text-sky-700 dark:text-sky-400"
          : "text-amber-700 dark:text-amber-400";
    const display =
      typeof value === "string" ? `"${value.length > 120 ? value.slice(0, 120) + "…" : value}"` : String(value);
    return (
      <div className="font-mono text-xs leading-6" style={{ paddingLeft: indent }}>
        <span className="text-brand-800 dark:text-brand-400">{name}: </span>
        <span className={color}>{display}</span>
      </div>
    );
  }

  const entries = Array.isArray(value)
    ? value.map((v, i) => [String(i), v] as const)
    : Object.entries(value as Record<string, unknown>);

  const preview = Array.isArray(value) ? `[${value.length}]` : `{${entries.length}}`;

  return (
    <div>
      <button
        type="button"
        className="flex w-full items-center gap-1 font-mono text-xs leading-6 hover:bg-surface-muted/50"
        style={{ paddingLeft: indent }}
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-ink-faint" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-ink-faint" />
        )}
        <span className="text-brand-800 dark:text-brand-400">{name}</span>
        <span className="text-ink-faint">{preview}</span>
      </button>
      {open &&
        entries.map(([k, v]) => (
          <TreeNode key={k} name={k} value={v} depth={depth + 1} />
        ))}
    </div>
  );
}
