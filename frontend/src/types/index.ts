export type ProviderStatus = "ok" | "degraded" | "error" | "disabled";

export interface HealthStatus {
  name: string;
  status: ProviderStatus;
  detail: string;
  configured: boolean;
}

export interface AppSettings {
  llm_provider: string;
  embedding_provider: string;
  vector_store: string;
  graph_store: string;
  ocr_enabled: boolean;
  openai_configured: boolean;
  gemini_configured: boolean;
  groq_configured?: boolean;
  huggingface_configured?: boolean;
  pinecone_configured: boolean;
  neo4j_configured: boolean;
  data_dir: string;
  output_dir: string;
}

export interface ProvidersHealthResponse {
  status: ProviderStatus;
  providers: HealthStatus[];
  settings: AppSettings;
}

export interface DocumentRecord {
  id: string;
  filename: string;
  original_filename: string;
  content_hash: string;
  file_size: number;
  page_count: number;
  status: string;
  ocr_used: boolean;
  pinecone_status: string;
  neo4j_status: string;
  extraction_status: string;
  duplicate_of: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProcessingJob {
  id: string;
  job_type: string;
  stage: string;
  status: string;
  logs: string[];
  error_message?: string | null;
}

export interface DocumentStatusResponse {
  document: DocumentRecord;
  latest_job: ProcessingJob | null;
}

export interface DashboardResponse {
  total_documents: number;
  fields_found: number;
  fields_missing: number;
  evidence_coverage: number;
  processing_documents: number;
  processed_documents: number;
  extracted_policies: number;
  average_confidence: number;
  fields_requiring_review: number;
  recent: Array<{
    id: string;
    filename: string;
    status: string;
    created_at: string;
    page_count: number;
    insurer: string | null;
    policy_type: string | null;
    fields_found: number;
    fields_missing: number;
    review_count: number;
  }>;
}

export interface EvidenceField {
  field_path: string;
  value?: unknown;
  status?: string;
  confidence?: number;
  evidence?: EvidenceItem[];
}

export interface EvidenceItem {
  source_file: string;
  page_number: number;
  quote: string;
  section?: string;
  parser?: string;
  retrieval_score?: number | null;
}

export interface GraphNode {
  id: string;
  labels?: string[];
  properties?: Record<string, unknown>;
}

export interface GraphRelationship {
  id?: string;
  type?: string;
  start?: string;
  end?: string;
  properties?: Record<string, unknown>;
}

export interface GraphResponse {
  policy_id?: string;
  nodes: GraphNode[];
  relationships: GraphRelationship[];
  available?: boolean;
  error?: string;
}

export interface CompareDifference {
  field_path: string;
  first: Record<string, unknown> | undefined;
  second: Record<string, unknown> | undefined;
}

export interface CompareResponse {
  first_document_id: string;
  second_document_id: string;
  difference_count: number;
  differences: CompareDifference[];
  graph_compare?: Record<string, unknown>;
}

export interface SearchResult {
  chunk_id: string;
  document_id: string;
  source_file: string;
  page_number: number;
  section: string;
  score: number;
  parser: string;
  text: string;
}

export interface ApiError {
  message: string;
  code?: string;
  status: number;
}

export type ExtractionPayload = Record<string, unknown>;
