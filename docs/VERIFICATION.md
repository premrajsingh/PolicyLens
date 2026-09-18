# Final verification

Reviewed 18 September 2026 against both supplied assignment documents.

- 59 backend tests passed; Ruff passed.
- Frontend TypeScript and production build passed; 3 frontend unit tests passed.
- Frontend npm audit: 0 known vulnerabilities at review time.
- 151 of 151 annotated acceptance checks passed across 4 unique PDFs.
- All 211 claimed fields had citations verified against the correct source PDF page.
- Five JSON outputs supplied; the second Liberty PDF is a duplicate alias.
- Live provider: Groq openai/gpt-oss-120b. Local hash embeddings, local vector store and local graph.
- Linux CPython 3.12 binary dependency resolution passed.

The live model outputs were passed through the same document-derived consistency and citation validation rules used by the application. Previously generated live responses were reused during validation-rule iteration to avoid extra API quota use. No expected-answer fixture is used by runtime extraction.

The original design was appropriate for the assignment, but the original results and implementation were not reliable enough to submit without corrections. Fixed areas include frontend build failure, current-versus-historical fields, sum-insured versus room caps, general-versus-regional maternity limits, TPA versus claims administrator, unsupported citations, conflict handling, typed normalization, stale extractions, failed jobs, document deletion, duplicate processing, local vector-store concurrency and guarded production access.

## Remaining verification limits

- These are development samples, not a held-out benchmark or a proof of generalization.
- Niva gross premium remains a source conflict: INR 98,476 on page 4 and INR 104,635 on page 6.
- Unknown and rejected fields remain visible with review flags. Missing prior-year facts are not guessed.
- The real samples are 3–6 pages. No 50–80-page accuracy benchmark was supplied.
- Docker could not be run: the daemon is unavailable and the Compose plugin is missing.
- Automated browser visual/end-to-end verification could not run: macOS sandbox blocked Chromium launch.
- No cloud deployment was provisioned. Optional Pinecone, Neo4j, Hugging Face, OpenAI and Gemini services were not revalidated end to end.
- Single-process jobs and SQLite are appropriate for a small protected review deployment. A multi-user production service needs durable queueing, user authorization and operational hardening.
