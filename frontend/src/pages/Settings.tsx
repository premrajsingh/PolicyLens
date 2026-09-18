import { useQuery } from "@tanstack/react-query";
import { Check, Loader2, Settings2, X } from "lucide-react";
import { api } from "../lib/api";
import { formatProviderDetail } from "../lib/labels";
import { ProviderStatusBadge } from "../components/StatusBadge";

export default function Settings() {
  const providers = useQuery({
    queryKey: ["providers-health"],
    queryFn: api.providersHealth,
    staleTime: 30_000,
    retry: 2,
  });

  if (providers.isLoading) {
    return (
      <div className="app-shell flex items-center justify-center py-24 text-ink-muted">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        Loading settings…
      </div>
    );
  }

  if (providers.isError || !providers.data) {
    return (
      <div className="app-shell">
        <div className="empty-state">
          <p className="text-sm text-ink-muted">Unable to load provider configuration.</p>
        </div>
      </div>
    );
  }

  const { settings, providers: providerList, status } = providers.data;

  const configRows: Array<{ label: string; value: string | boolean }> = [
    { label: "LLM provider", value: settings.llm_provider },
    { label: "Embedding provider", value: settings.embedding_provider },
    { label: "Vector store", value: settings.vector_store },
    { label: "Graph store", value: settings.graph_store },
    { label: "OCR enabled", value: settings.ocr_enabled },
    { label: "OpenAI configured", value: settings.openai_configured },
    { label: "Gemini configured", value: settings.gemini_configured },
    { label: "Groq configured", value: Boolean(settings.groq_configured) },
    { label: "Hugging Face configured", value: Boolean(settings.huggingface_configured) },
    { label: "Pinecone configured", value: settings.pinecone_configured },
    { label: "Neo4j configured", value: settings.neo4j_configured },
    { label: "Data directory", value: shortenPath(settings.data_dir) },
    { label: "Output directory", value: shortenPath(settings.output_dir) },
  ];

  return (
    <div className="app-shell space-y-6">
      <header>
        <div className="flex items-center gap-3">
          <div className="rounded-md bg-brand-700/10 p-2 text-brand-700">
            <Settings2 className="h-5 w-5" />
          </div>
          <div>
            <h1 className="page-title">Settings</h1>
            <p className="mt-0.5 text-sm text-ink-muted">
              Provider configuration and system status — secrets are never displayed
            </p>
          </div>
        </div>
      </header>

      <section className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">System status</h2>
          <ProviderStatusBadge status={status} />
        </div>
        <div className="divide-y divide-border">
          {providerList.map((p) => (
            <div key={p.name} className="flex items-start justify-between gap-4 px-5 py-4">
              <div className="min-w-0">
                <div className="text-sm font-medium capitalize text-ink">
                  {p.name.replace(/_/g, " ")}
                </div>
                <div className="mt-0.5 text-xs text-ink-faint">
                  Configured: {p.configured ? "Yes" : "No"}
                </div>
                {p.detail && (
                  <div className="mt-1 text-xs text-ink-muted">
                    {formatProviderDetail(p.detail)}
                  </div>
                )}
              </div>
              <ProviderStatusBadge status={p.status} />
            </div>
          ))}
        </div>
      </section>

      <section className="card overflow-hidden">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold text-ink">Configuration</h2>
          <p className="mt-1 text-xs text-ink-faint">
            Boolean flags indicate whether credentials are set — actual keys are never exposed.
          </p>
        </div>
        <table className="w-full text-left text-sm">
          <tbody className="divide-y divide-border">
            {configRows.map((row) => (
              <tr key={row.label} className="hover:bg-surface-muted/30">
                <td className="px-5 py-3 font-medium text-ink-muted">{row.label}</td>
                <td className="px-5 py-3 text-ink">
                  {typeof row.value === "boolean" ? (
                    <BooleanIndicator value={row.value} />
                  ) : (
                    <span className="font-mono text-xs">{row.value}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function BooleanIndicator({ value }: { value: boolean }) {
  return value ? (
    <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
      <Check className="h-4 w-4" />
      Yes
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-ink-faint">
      <X className="h-4 w-4" />
      No
    </span>
  );
}

function shortenPath(path: string): string {
  if (!path) return "—";
  const parts = path.replace(/\\/g, "/").split("/");
  if (parts.length <= 3) return path;
  return `…/${parts.slice(-3).join("/")}`;
}
