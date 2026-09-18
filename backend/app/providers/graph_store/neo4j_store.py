from __future__ import annotations

import logging
from typing import Any

from app.models.schema import ExtractedPolicy, HealthStatus
from app.providers.graph_store.local import _walk_fields

logger = logging.getLogger(__name__)

CONSTRAINTS = [
    "CREATE CONSTRAINT policy_id IF NOT EXISTS FOR (p:Policy) REQUIRE p.policy_id IS UNIQUE",
    "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (e:Evidence) REQUIRE e.evidence_id IS UNIQUE",
]


class Neo4jPolicyGraph:
    def __init__(
        self,
        *,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        if not password:
            raise ValueError("NEO4J_PASSWORD is required when GRAPH_STORE=neo4j")
        from neo4j import AsyncGraphDatabase

        self.uri = uri
        self.username = username
        self.database = database
        self._driver = AsyncGraphDatabase.driver(uri, auth=(username, password))

    async def close(self) -> None:
        await self._driver.close()

    async def ensure_schema(self) -> None:
        async with self._driver.session(database=self.database) as session:
            for stmt in CONSTRAINTS:
                await session.run(stmt)

    async def upsert_policy(self, policy: ExtractedPolicy) -> None:
        await self.ensure_schema()
        policy_id = policy.document.document_id
        fields = _walk_fields(policy)
        async with self._driver.session(database=self.database) as session:
            await session.run(
                """
                MERGE (p:Policy {policy_id: $policy_id})
                SET p.document_id = $document_id,
                    p.source_file = $source_file,
                    p.status = $status,
                    p.confidence = $confidence,
                    p.created_at = coalesce(p.created_at, datetime())
                """,
                {
                    "policy_id": policy_id,
                    "document_id": policy.document.document_id,
                    "source_file": policy.document.filename,
                    "status": "validated",
                    "confidence": policy.validation.overall_confidence,
                },
            )
            if policy.insurer.value:
                await session.run(
                    """
                    MERGE (i:Insurer {name: $name})
                    WITH i
                    MATCH (p:Policy {policy_id: $policy_id})
                    MERGE (p)-[:ISSUED_BY]->(i)
                    """,
                    {"name": str(policy.insurer.value), "policy_id": policy_id},
                )
            if policy.tpa.value:
                await session.run(
                    """
                    MERGE (t:TPA {name: $name})
                    WITH t
                    MATCH (p:Policy {policy_id: $policy_id})
                    MERGE (p)-[:ADMINISTERED_BY]->(t)
                    """,
                    {"name": str(policy.tpa.value), "policy_id": policy_id},
                )
            for field in fields:
                label = (
                    "WaitingPeriod"
                    if field["field_path"].startswith("waiting_periods")
                    else "Benefit"
                )
                await session.run(
                    f"""
                    MATCH (p:Policy {{policy_id: $policy_id}})
                    MERGE (b:{label} {{policy_id: $policy_id, field_path: $field_path}})
                    SET b.value = $value,
                        b.status = $status,
                        b.confidence = $confidence,
                        b.document_id = $document_id,
                        b.source_file = $source_file
                    MERGE (p)-[:HAS_BENEFIT]->(b)
                    """,
                    {
                        "policy_id": policy_id,
                        "field_path": field["field_path"],
                        "value": str(field.get("value")),
                        "status": field.get("status"),
                        "confidence": field.get("confidence"),
                        "document_id": policy.document.document_id,
                        "source_file": policy.document.filename,
                    },
                )
                for idx, ev in enumerate(field.get("evidence") or []):
                    evidence_id = f"{policy_id}:{field['field_path']}:{idx}"
                    await session.run(
                        """
                        MATCH (b {policy_id: $policy_id, field_path: $field_path})
                        MERGE (e:Evidence {evidence_id: $evidence_id})
                        SET e.page_number = $page_number,
                            e.quote = $quote,
                            e.source_file = $source_file,
                            e.parser = $parser,
                            e.document_id = $document_id,
                            e.policy_id = $policy_id
                        MERGE (b)-[:SUPPORTED_BY]->(e)
                        """,
                        {
                            "policy_id": policy_id,
                            "field_path": field["field_path"],
                            "evidence_id": evidence_id,
                            "page_number": ev.get("page_number"),
                            "quote": ev.get("quote"),
                            "source_file": ev.get("source_file"),
                            "parser": ev.get("parser"),
                            "document_id": policy.document.document_id,
                        },
                    )

    async def get_policy_graph(self, policy_id: str) -> dict:
        async with self._driver.session(database=self.database) as session:
            result = await session.run(
                """
                MATCH (p:Policy {policy_id: $policy_id})
                OPTIONAL MATCH (p)-[r]->(n)
                RETURN p, collect({rel: type(r), node: n}) AS links
                """,
                {"policy_id": policy_id},
            )
            record = await result.single()
            if not record:
                return {
                    "policy_id": policy_id,
                    "nodes": [],
                    "relationships": [],
                    "available": False,
                }
            nodes = [{"id": policy_id, "label": "Policy", "properties": dict(record["p"])}]
            relationships = []
            for link in record["links"]:
                if not link.get("node"):
                    continue
                node = dict(link["node"])
                nid = node.get("field_path") or node.get("name") or node.get("evidence_id")
                nodes.append(
                    {"id": str(nid), "label": list(link["node"].labels)[0], "properties": node}
                )
                relationships.append({"type": link["rel"], "from": policy_id, "to": str(nid)})
            return {
                "policy_id": policy_id,
                "nodes": nodes,
                "relationships": relationships,
                "available": True,
                "store": "neo4j",
            }

    async def compare_policies(self, first_policy_id: str, second_policy_id: str) -> dict:
        a = await self.get_policy_graph(first_policy_id)
        b = await self.get_policy_graph(second_policy_id)

        def field_map(graph: dict) -> dict[str, Any]:
            out = {}
            for n in graph.get("nodes", []):
                props = n.get("properties") or {}
                if "field_path" in props:
                    out[props["field_path"]] = props
            return out

        am, bm = field_map(a), field_map(b)
        diffs = []
        for key in sorted(set(am) | set(bm)):
            if (am.get(key) or {}).get("value") != (bm.get(key) or {}).get("value"):
                diffs.append({"field_path": key, "first": am.get(key), "second": bm.get(key)})
        return {
            "first_policy_id": first_policy_id,
            "second_policy_id": second_policy_id,
            "differences": diffs,
            "store": "neo4j",
        }

    async def delete_policy(self, policy_id: str) -> None:
        async with self._driver.session(database=self.database) as session:
            await session.run(
                """
                MATCH (n {policy_id: $policy_id})
                DETACH DELETE n
                """,
                {"policy_id": policy_id},
            )

    async def healthcheck(self) -> HealthStatus:
        try:
            async with self._driver.session(database=self.database) as session:
                await session.run("RETURN 1 AS ok")
            return HealthStatus(
                name="neo4j",
                status="ok",
                detail=f"uri={self.uri} database={self.database}",
                configured=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("neo4j_healthcheck_failed")
            return HealthStatus(
                name="neo4j",
                status="error",
                detail=str(exc)[:300],
                configured=True,
            )
