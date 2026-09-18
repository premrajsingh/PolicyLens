# Known Limitations

1. **Mock LLM** returns schema-valid unknown fields and does not perform full GMC extraction. Configure `LLM_PROVIDER=openai` or `gemini` with API keys for richer field fill from retrieved evidence.
2. **OCR** requires system Tesseract. Without it (or with `OCR_ENABLED=false`), scanned/low-text pages stay sparse and related fields stay `unknown`.
3. **Hash embeddings** are deterministic offline stand-ins. For stronger semantic retrieval, install `sentence-transformers` and set `EMBEDDING_PROVIDER=local`.
4. **Duplicate samples**: `Policy liberty 2022-2023.pdf` and `Net Catalyst - GPA - Policy Copy - 2022-23.pdf` are byte-identical; the app records duplicates by SHA-256.
5. **GPA-titled policies** may lack full GMC maternity schedules; missing clauses correctly surface as `unknown` / `not_applicable` rather than invented coverage.
6. **Camelot** is optional; table extraction primarily uses pdfplumber. Complex scanned tables may need OCR + LLM.
7. **Pinecone / Neo4j** were not exercised against live cloud instances in the default verification run. Unit/adapter tests cover missing-config refusal and local fallbacks.
8. **Accuracy** is not claimed as a percentage. Evaluate using evidence coverage, conflict counts, and human review of `fields_requiring_review`.
9. **Conflict resolution** never silently picks a winner; conflicts remain `status=conflict` with evidence retained.
10. Frontend dark mode is CSS-variable based; visual polish focuses on light B2B teal/slate branding.
