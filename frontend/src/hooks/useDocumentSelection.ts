import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { DocumentRecord } from "../types";

/**
 * Keep `?doc=` in sync with the dropdown. When the URL has no doc,
 * auto-pick the best GMC demo document (never prefer GPA first).
 */
export function useDocumentSelection(documents: DocumentRecord[] | undefined) {
  const [searchParams, setSearchParams] = useSearchParams();
  const paramId = searchParams.get("doc") ?? "";
  const enabled = documents !== undefined;

  const selectable = useMemo(() => {
    if (!documents?.length) return [];
    return documents.filter((d) => d.status !== "duplicate");
  }, [documents]);

  const preferredId = useMemo(() => {
    if (!selectable.length) return "";
    const score = (d: DocumentRecord) => {
      let s = 0;
      if (d.extraction_status === "extracted" || d.status === "extracted") s += 40;
      if (d.pinecone_status === "indexed" || d.pinecone_status === "local_indexed") s += 10;
      if (d.neo4j_status === "synced" || d.neo4j_status === "local_synced") s += 10;
      const name = (d.original_filename || d.filename || "").toLowerCase();
      // Strong GMC preference for manager demo
      if (name.includes("ghi")) s += 50;
      if (name.includes("1.policy") || name.startsWith("1.policy") || name.includes("policy copy.pdf"))
        s += 45;
      if (name.includes("niva") || name.includes("gmc renewal")) s += 15;
      // Deprioritize sparse GPA / liberty duplicates
      if (name.includes("gpa") || name.includes("net catalyst") || name.includes("liberty")) s -= 80;
      return s;
    };
    return [...selectable].sort((a, b) => score(b) - score(a))[0]?.id ?? "";
  }, [selectable]);

  useEffect(() => {
    if (!enabled) return;
    if (!selectable.length) return;
    if (paramId && selectable.some((d) => d.id === paramId)) return;
    if (paramId && !selectable.some((d) => d.id === paramId) && preferredId) {
      setSearchParams({ doc: preferredId }, { replace: true });
      return;
    }
    if (!paramId && preferredId) {
      setSearchParams({ doc: preferredId }, { replace: true });
    }
  }, [enabled, paramId, preferredId, selectable, setSearchParams]);

  const selectedId =
    paramId && selectable.some((d) => d.id === paramId) ? paramId : preferredId || paramId;

  return {
    selectedId: enabled ? selectedId : paramId,
    setSelectedId: (id: string) => {
      if (id) setSearchParams({ doc: id });
      else setSearchParams({});
    },
    selectable,
  };
}
