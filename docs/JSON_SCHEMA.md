# JSON Schema

Schema version: `1.1.0`  
Pipeline version: see `app.core.version.PIPELINE_VERSION`

Generated JSON Schema: [`docs/QMS_SCHEMA.json`](QMS_SCHEMA.json)

## FieldValue envelope

Every extractable leaf uses:

```json
{
  "value": null,
  "normalized_value": null,
  "status": "unknown",
  "raw_text": null,
  "conditions": [],
  "confidence": 0.0,
  "evidence": [],
  "warnings": [],
  "conflicts": []
}
```

### Status enum

`covered` | `not_covered` | `waived_off` | `applied` | `not_applicable` | `unknown` | `conflict` | `partially_covered`

### Evidence item

```json
{
  "source_file": "GHI Policy.pdf",
  "page_number": 8,
  "quote": "exact supporting quote",
  "section": "maternity",
  "parser": "text",
  "retrieval_score": null
}
```

## Top-level document

- `schema_version`, `pipeline_version`
- `document` — id, filename, hash, page_count, ocr_used, parsers
- `insurer`, `tpa`, `claims_administrator`, `policy_type`, `policy_number`, `group_company_name`
- `current_policy` — current period dates, inception, net/gross premium, aggregate SI
- `previous_policy` — dates, tenure, premiums, raw period text (only when explicitly historical)
- `policy_structure` — family members, conditions, sum insured tiers
- `demographics` — counts + total lives
- `hospitalization` — room/ICU/pre/post
- `maternity`
- `waiting_periods`
- `other_benefits`
- `infertility_and_ambulance`
- `buffer_and_waivers`
- `extraction_metadata` — provider, model, timings, indexing/sync status, completion_status
- `validation` — confidence, coverage, conflicts, review fields

Authoritative output is this JSON. Neo4j mirrors validated facts only.
