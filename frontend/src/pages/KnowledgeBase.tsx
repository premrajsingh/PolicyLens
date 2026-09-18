import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ComponentType, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { api, formatBytes, formatDate } from "../lib/api";
import { displayFilename } from "../lib/labels";
import StatusBadge from "../components/StatusBadge";
import UploadDropzone from "../components/UploadDropzone";

export default function KnowledgeBase() {
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [pipelineHint, setPipelineHint] = useState<string | null>(null);
  const [watchIds, setWatchIds] = useState<string[]>([]);
  const queryClient = useQueryClient();

  const documents = useQuery({
    queryKey: ["documents", debouncedSearch],
    queryFn: () => api.listDocuments(debouncedSearch || undefined),
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (!watchIds.length || !documents.data?.documents) return;
    const stillRunning = watchIds.filter((id) => {
      const doc = documents.data.documents.find((d) => d.id === id);
      if (!doc) return false;
      return !["extracted", "partial", "error"].includes(doc.status);
    });
    if (stillRunning.length === 0) {
      setWatchIds([]);
      setPipelineHint("Processing finished. Open each policy to review results and any errors.");
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    } else {
      setPipelineHint(
        `Auto-pipeline running for ${stillRunning.length} document(s): reading policy pages and checking answers…`,
      );
    }
  }, [documents.data, watchIds, queryClient]);

  const uploadMutation = useMutation({
    mutationFn: api.uploadDocuments,
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      const auto = (res as { auto_pipeline?: string[] }).auto_pipeline ?? [];
      const docs = res.documents ?? [];
      const dups = docs.filter((d) => d.status === "duplicate");
      if (auto.length) {
        setWatchIds(auto);
        setPipelineHint(
          `Uploaded ${auto.length} new PDF(s). Reading and extraction started automatically.`,
        );
      } else if (dups.length) {
        setPipelineHint(
          `${dups.length} file(s) were duplicates of documents already in the knowledge base.`,
        );
      }
    },
  });

  const processMutation = useMutation({
    mutationFn: async ({ id, reprocess }: { id: string; reprocess?: boolean }) => {
      if (reprocess) {
        await api.reprocessDocument(id);
        return { id, mode: "reprocess" as const };
      }
      await api.retryDocument(id);
      return { id, mode: "retry" as const };
    },
    onSuccess: (_data, vars) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      setWatchIds((prev) => Array.from(new Set([...prev, vars.id])));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: api.deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    setDebouncedSearch(search.trim());
  };

  return (
    <div className="app-shell space-y-6">
      <header>
        <h1 className="page-title">Policies</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Upload GMC policy PDFs. New files are indexed and extracted automatically.
        </p>
      </header>

      <UploadDropzone
        onUpload={(files) => uploadMutation.mutate(files)}
        uploading={uploadMutation.isPending}
      />

      {uploadMutation.isError && (
        <ErrorBanner message={(uploadMutation.error as Error).message} />
      )}
      {(processMutation.isError || deleteMutation.isError) && <ErrorBanner message={processMutation.error?.message || deleteMutation.error?.message || "Request failed"}/>}
      {pipelineHint && (
        <div className="flex items-start gap-2 rounded-lg bg-sky-50 px-4 py-3 text-sm text-sky-900 dark:bg-sky-900/20 dark:text-sky-100">
          {watchIds.length ? (
            <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
          ) : (
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          )}
          {pipelineHint}
        </div>
      )}

      <div className="card overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-border px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-sm font-semibold text-ink">Documents</h2>
          <form onSubmit={handleSearch} className="flex gap-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
              <input
                aria-label="Search policies"
                type="search"
                className="input pl-9 sm:w-64"
                placeholder="Search by filename or status…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <button type="submit" className="btn-secondary">
              Search
            </button>
          </form>
        </div>

        {documents.isLoading ? (
          <div className="flex items-center justify-center py-16 text-ink-muted">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Loading documents…
          </div>
        ) : documents.isError ? (
          <div className="px-5 py-8 text-center text-sm text-red-600">
            Failed to load documents
          </div>
        ) : !documents.data?.documents.length ? (
          <div className="empty-state mx-5 my-8 border-0 bg-transparent">
            <p className="text-sm text-ink-muted">
              {debouncedSearch
                ? "No documents match your search."
                : "No documents uploaded yet. Drop PDFs above to get started."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[800px] text-left text-sm">
              <thead className="bg-surface-muted/60 text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Document</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Pipeline</th>
                  <th className="px-5 py-3 font-medium">Pages</th>
                  <th className="px-5 py-3 font-medium">Uploaded</th>
                  <th className="px-5 py-3 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {documents.data.documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-surface-muted/30">
                    <td className="px-5 py-3">
                      <Link
                        to={`/workspace?doc=${doc.id}`}
                        className="font-medium text-ink hover:text-brand-700"
                      >
                        {displayFilename(doc.original_filename || doc.filename)}
                      </Link>
                      <div className="text-xs text-ink-faint">{formatBytes(doc.file_size)}</div>
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap gap-1">
                        {doc.ocr_used && <StatusBadge status="complete" variant="ocr" />}
                        <StatusBadge status={doc.pinecone_status} variant="pinecone" />
                        <StatusBadge status={doc.neo4j_status} variant="neo4j" />
                        <StatusBadge status={doc.extraction_status} variant="extraction" />
                      </div>
                    </td>
                    <td className="px-5 py-3 text-ink-muted">{doc.page_count || "—"}</td>
                    <td className="px-5 py-3 text-ink-muted">{formatDate(doc.created_at)}</td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1">
                        {doc.status !== "duplicate" && (
                          <>
                            <ActionButton
                              title="Retry extraction"
                              onClick={() => processMutation.mutate({ id: doc.id })}
                              loading={processMutation.isPending || ["queued","processing","uploaded"].includes(doc.status)}
                              icon={Play}
                            />
                            <ActionButton
                              title="Reprocess from scratch"
                              onClick={() =>
                                processMutation.mutate({ id: doc.id, reprocess: true })
                              }
                              loading={processMutation.isPending || ["queued","processing","uploaded"].includes(doc.status)}
                              icon={RefreshCw}
                            />
                          </>
                        )}
                        <ActionButton
                          title="Delete"
                          onClick={() => {
                            if (confirm(`Delete "${displayFilename(doc.original_filename || doc.filename)}"?`)) {
                              deleteMutation.mutate(doc.id);
                            }
                          }}
                          loading={deleteMutation.isPending}
                          icon={Trash2}
                          danger
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function ActionButton({
  title,
  onClick,
  loading,
  icon: Icon,
  danger = false,
}: {
  title: string;
  onClick: () => void;
  loading: boolean;
  icon: ComponentType<{ className?: string }>;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      className={`btn-ghost p-2 ${danger ? "hover:text-red-600" : ""}`}
      onClick={onClick}
      disabled={loading}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
      <AlertCircle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}
