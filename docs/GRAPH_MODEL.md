# Graph Model

Neo4j is an explainability and relationship layer. **QMS JSON remains authoritative.**

## Nodes

`Policy`, `Insurer`, `TPA`, `Benefit`, `WaitingPeriod`, `CoverageLimit`, `Condition`, `FamilyCategory`, `SumInsuredTier`, `Evidence`

Common properties: `policy_id`, `document_id`, `source_file`, `field_path`, `status`, `confidence`, `created_at`

## Relationships

- `(:Policy)-[:ISSUED_BY]->(:Insurer)`
- `(:Policy)-[:ADMINISTERED_BY]->(:TPA)`
- `(:Policy)-[:HAS_BENEFIT]->(:Benefit)`
- `(:Policy)-[:HAS_WAITING_PERIOD]->(:WaitingPeriod)`
- `(:Policy)-[:HAS_FAMILY_CATEGORY]->(:FamilyCategory)`
- `(:Policy)-[:HAS_SUM_INSURED]->(:SumInsuredTier)`
- `(:Benefit)-[:HAS_LIMIT]->(:CoverageLimit)`
- `(:Benefit)-[:HAS_CONDITION]->(:Condition)`
- `(:Benefit)-[:SUPPORTED_BY]->(:Evidence)`
- `(:WaitingPeriod)-[:SUPPORTED_BY]->(:Evidence)`

## Write rules

1. Parameterized Cypher only
2. Constraints/indexes created safely on startup
3. Idempotent MERGE on stable keys (`policy_id`, `field_path`, evidence hash)
4. Never write unvalidated LLM output
5. Delete by `policy_id` / `document_id`
6. LocalGraphStore mirrors the same logical model in JSON for offline mode
