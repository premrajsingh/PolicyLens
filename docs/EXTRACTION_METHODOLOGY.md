# Extraction Methodology

## Pipeline stages

1. **parsing** — PyMuPDF page text; preserve page numbers and raw text
2. **ocr** — If page text chars < `OCR_MIN_TEXT_CHARS` and OCR enabled, run pytesseract; mark parser=`ocr`
3. **chunking** — Overlapping text/table chunks with section hints and aliases
4. **embedding** — Local (or external) embeddings; dimension must match Pinecone index
5. **indexing** — Upsert to vector store with deterministic IDs
6. **retrieval** — Lexical FTS5 + semantic search; merge/normalize; filter by document_id and section
7. **structured_extraction** — LLM returns JSON per field group with evidence quotes
8. **validation** — Schema, evidence presence, conflicts, normalization, confidence
9. **neo4j_sync** — Write only validated facts
10. **complete**

## Evidence rules

- Heading alone is not coverage proof
- Quote must appear in stored page text (normalized whitespace check)
- Exclusions stored separately from coverage
- Group-specific schedules/endorsements preferred over general wording when both retrieved
- Conflicting credible evidence ? `status=conflict`, `value=null`

## Field groups

`identity`, `previous_policy`, `policy_structure`, `demographics`, `room_hospitalization`, `maternity`, `waiting_periods`, `other_benefits`, `infertility_ambulance`, `buffer_waivers`

## Terminology aliases (examples)

- pre-existing disease / PED / existing illness
- room rent / accommodation limit
- ICU / intensive care unit
- maternity / childbirth benefit
- ambulance / road ambulance
- corporate buffer / group buffer

Aliases expand queries only; they do not invent output values.

## LLM failure handling

Invalid JSON ? retry once with validation feedback ? mark fields `unknown` on persistent failure. Never silently invent unsupported values.
