from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.schema import ExtractedPolicy, FieldValue, HealthStatus


def _field_snapshot(path: str, field: FieldValue) -> dict[str, Any] | None:
    if field.value is None and field.status in {"unknown", "not_applicable"}:
        return None
    return {
        "field_path": path,
        "value": field.value,
        "normalized_value": field.normalized_value,
        "status": field.status,
        "confidence": field.confidence,
        "evidence": [e.model_dump() for e in field.evidence],
    }


def _walk_fields(policy: ExtractedPolicy) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    top = {
        "insurer": policy.insurer,
        "tpa": policy.tpa,
        "claims_administrator": policy.claims_administrator,
        "policy_type": policy.policy_type,
        "policy_number": policy.policy_number,
        "group_company_name": policy.group_company_name,
    }
    for key, field in top.items():
        snap = _field_snapshot(key, field)
        if snap:
            items.append(snap)

    groups = {
        "current_policy": policy.current_policy,
        "previous_policy": policy.previous_policy,
        "policy_structure": policy.policy_structure,
        "demographics": policy.demographics,
        "hospitalization": policy.hospitalization,
        "maternity": policy.maternity,
        "waiting_periods": policy.waiting_periods,
        "other_benefits": policy.other_benefits,
        "infertility_and_ambulance": policy.infertility_and_ambulance,
        "buffer_and_waivers": policy.buffer_and_waivers,
    }
    for group_name, group in groups.items():
        for field_name, field in group.model_dump().items():
            fv = FieldValue.model_validate(field)
            snap = _field_snapshot(f"{group_name}.{field_name}", fv)
            if snap:
                items.append(snap)
    return items


class LocalGraphStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, policy_id: str) -> Path:
        return self.root / f"{policy_id}.json"

    async def upsert_policy(self, policy: ExtractedPolicy) -> None:
        payload = {
            "policy_id": policy.document.document_id,
            "document_id": policy.document.document_id,
            "source_file": policy.document.filename,
            "insurer": policy.insurer.value,
            "tpa": policy.tpa.value,
            "fields": _walk_fields(policy),
            "validation": policy.validation.model_dump(),
        }
        self._path(policy.document.document_id).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    async def get_policy_graph(self, policy_id: str) -> dict:
        path = self._path(policy_id)
        if not path.exists():
            return {"policy_id": policy_id, "nodes": [], "relationships": [], "available": False}
        data = json.loads(path.read_text(encoding="utf-8"))
        nodes = [
            {"id": policy_id, "label": "Policy", "properties": {"source_file": data["source_file"]}}
        ]
        relationships = []
        if data.get("insurer"):
            nodes.append(
                {
                    "id": f"insurer-{policy_id}",
                    "label": "Insurer",
                    "properties": {"name": data["insurer"]},
                }
            )
            relationships.append(
                {"type": "ISSUED_BY", "from": policy_id, "to": f"insurer-{policy_id}"}
            )
        if data.get("tpa"):
            nodes.append(
                {"id": f"tpa-{policy_id}", "label": "TPA", "properties": {"name": data["tpa"]}}
            )
            relationships.append(
                {"type": "ADMINISTERED_BY", "from": policy_id, "to": f"tpa-{policy_id}"}
            )
        for field in data.get("fields", []):
            fid = f"{policy_id}-{field['field_path']}"
            nodes.append(
                {
                    "id": fid,
                    "label": "Benefit" if "waiting" not in field["field_path"] else "WaitingPeriod",
                    "properties": field,
                }
            )
            relationships.append({"type": "HAS_BENEFIT", "from": policy_id, "to": fid})
            for idx, ev in enumerate(field.get("evidence") or []):
                eid = f"{fid}-ev-{idx}"
                nodes.append({"id": eid, "label": "Evidence", "properties": ev})
                relationships.append({"type": "SUPPORTED_BY", "from": fid, "to": eid})
        return {
            "policy_id": policy_id,
            "nodes": nodes,
            "relationships": relationships,
            "available": True,
            "store": "local",
        }

    async def compare_policies(self, first_policy_id: str, second_policy_id: str) -> dict:
        a = await self.get_policy_graph(first_policy_id)
        b = await self.get_policy_graph(second_policy_id)
        a_fields = {
            n["properties"]["field_path"]: n["properties"]
            for n in a.get("nodes", [])
            if n["label"] in {"Benefit", "WaitingPeriod"}
            and "field_path" in n.get("properties", {})
        }
        b_fields = {
            n["properties"]["field_path"]: n["properties"]
            for n in b.get("nodes", [])
            if n["label"] in {"Benefit", "WaitingPeriod"}
            and "field_path" in n.get("properties", {})
        }
        keys = sorted(set(a_fields) | set(b_fields))
        diffs = []
        for key in keys:
            left = a_fields.get(key)
            right = b_fields.get(key)
            if (left or {}).get("value") != (right or {}).get("value") or (left or {}).get(
                "status"
            ) != (right or {}).get("status"):
                diffs.append({"field_path": key, "first": left, "second": right})
        return {
            "first_policy_id": first_policy_id,
            "second_policy_id": second_policy_id,
            "differences": diffs,
            "store": "local",
        }

    async def delete_policy(self, policy_id: str) -> None:
        path = self._path(policy_id)
        if path.exists():
            path.unlink()

    async def healthcheck(self) -> HealthStatus:
        count = len(list(self.root.glob("*.json")))
        return HealthStatus(
            name="local_graph_store",
            status="ok",
            detail=f"{count} policies at {self.root}",
            configured=True,
        )
