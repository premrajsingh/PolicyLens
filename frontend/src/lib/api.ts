import type {
  CompareResponse,
  DashboardResponse,
  DocumentRecord,
  DocumentStatusResponse,
  EvidenceField,
  ExtractionPayload,
  ProvidersHealthResponse,
  SearchResult,
} from "../types";

const ROOT = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const API_BASE = ROOT ? `${ROOT.replace(/\/api$/, "")}/api` : "/api";
export const apiUrl = (path: string) => `${API_BASE}${path}`;

export class ApiClientError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
  }
}

async function parseError(res: Response): Promise<ApiClientError> {
  let message = res.statusText || "Request failed";
  let code: string | undefined;
  try {
    const body = await res.json();
    message = body.error?.message ?? body.detail ?? body.message ?? message;
    if (typeof message !== "string") message = "The request could not be completed.";
    code = body.error?.code ?? body.code;
  } catch {
    /* ignore */
  }
  return new ApiClientError(message, res.status, code);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  const contentType = res.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return res.json() as Promise<T>;
  return res.text() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; app: string }>("/health"),

  dashboard: () => request<DashboardResponse>("/dashboard"),

  providersHealth: () => request<ProvidersHealthResponse>("/providers/health"),

  listDocuments: (q?: string) =>
    request<{ documents: DocumentRecord[] }>(
      `/documents${q ? `?q=${encodeURIComponent(q)}` : ""}`,
    ),

  getDocument: (id: string) => request<DocumentRecord>(`/documents/${id}`),

  uploadDocuments: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return request<{ documents: DocumentRecord[]; auto_pipeline?: string[] }>("/documents/upload", {
      method: "POST",
      body: form,
    });
  },

  retryDocument: (id: string) => request<{document_id: string; status: string}>(`/documents/${id}/retry`, {method: "POST"}),

  deleteDocument: (id: string) =>
    request<{ deleted: string }>(`/documents/${id}`, { method: "DELETE" }),

  processDocument: (id: string) =>
    request<{ job_id: string; status: string; stage: string; logs: string[] }>(
      `/documents/${id}/process`,
      { method: "POST" },
    ),

  reprocessDocument: (id: string) =>
    request<{ job_id: string; status: string; stage: string; logs: string[] }>(
      `/documents/${id}/reprocess`,
      { method: "POST" },
    ),

  documentStatus: (id: string) =>
    request<DocumentStatusResponse>(`/documents/${id}/status`),

  extractPolicy: (id: string) =>
    request<ExtractionPayload>(`/policies/${id}/extract`, { method: "POST" }),

  getExtraction: (id: string) =>
    request<ExtractionPayload>(`/policies/${id}/extraction`),

  getEvidence: (id: string) =>
    request<{ document_id: string; fields: EvidenceField[] }>(
      `/policies/${id}/evidence`,
    ),

  getValidation: (id: string) =>
    request<Record<string, unknown>>(`/policies/${id}/validation`),

  compare: (firstId: string, secondId: string) =>
    request<CompareResponse>("/compare", {
      method: "POST",
      body: JSON.stringify({
        first_document_id: firstId,
        second_document_id: secondId,
      }),
    }),

  search: (query: string, documentId?: string) =>
    request<{ query: string; results: SearchResult[] }>("/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        document_id: documentId ?? null,
        top_k: 8,
      }),
    }),
};

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}
