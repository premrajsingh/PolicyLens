from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from app.db.models import (
    DocumentChunk,
    DocumentPage,
    ExtractionResult,
    ProcessingJob,
    ValidationResult,
)
from app.db.session import get_engine
from app.extraction.fields import mine_field_from_evidence
from app.extraction.normalize import (
    normalize_currency,
    normalize_duration,
    normalize_field,
    normalize_status,
)
from app.extraction.pipeline import PipelineService
from app.extraction.semantics import apply_schema_rules
from app.models.schema import (
    DocumentInfo,
    EvidenceItem,
    ExtractedPolicy,
    ExtractionMetadata,
    FieldValue,
)
from app.providers.vector_store.base import Chunk
from app.providers.vector_store.local import LocalVectorStore
from app.retrieval.hybrid import lexical_search
from app.validation.engine import validate_and_score

pytest_plugins = ["test_core"]


def policy(**kwargs):
    return ExtractedPolicy(
        schema_version="1.1.0",
        pipeline_version="0.2.0",
        document=DocumentInfo(document_id="d", filename="a.pdf", content_hash="h"),
        extraction_metadata=ExtractionMetadata(provider="mock", generated_at="t"),
        **kwargs,
    )


def claim(quote="ICU 2%", page=1, source="a.pdf", **kwargs):
    return FieldValue(
        value="2%",
        normalized_value=2,
        status="covered",
        evidence=[EvidenceItem(source_file=source, page_number=page, quote=quote)],
        **kwargs,
    )


@pytest.mark.parametrize(
    "text", ["30 days", "01-Apr-2023", "Room rent 2%", "Policy 123456", "9 months"]
)
def test_non_currency_numbers_are_not_money(text):
    assert normalize_currency(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("INR 5 Lakhs", 500000),
        ("Rs. 1.5 crore", 15000000),
        ("0", 0),
        ("Rs. 0", 0),
        ("2.5 lakh", 250000),
    ],
)
def test_currency_units(text, expected):
    assert normalize_currency(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("not waived", "applied"),
        ("not applicable", "not_applicable"),
        ("waiver not applicable", "applied"),
        ("exclusion condition waived", "waived_off"),
        ("exclusion heading", None),
        ("day one", None),
    ],
)
def test_negation_and_headings(text, expected):
    assert normalize_status(text) == expected


def test_duration_needs_unit():
    assert normalize_duration("someone in the second section") is None


def test_normalizers_respect_field_types():
    f = FieldValue(value="01-Apr-2023", status="covered")
    assert normalize_field("policy_period_end", f).normalized_value == "2023-04-01"
    f = FieldValue(value="30 days", status="covered")
    assert normalize_field("pre_hospitalization_days", f).normalized_value == 30
    f = FieldValue(value="ABC-1234", status="covered")
    assert normalize_field("policy_number", f).normalized_value == "ABC-1234"


@pytest.mark.parametrize(
    ("field", "pages"),
    [
        (claim(page=9), {1: "ICU 2%"}),
        (claim(source="other.pdf"), {1: "ICU 2%"}),
        (claim(quote="ICU covered 2%"), {1: "ICU excluded. Room rent 2%."}),
    ],
)
def test_wrong_page_source_or_rewritten_claim_is_rejected(field, pages):
    p = policy()
    p.hospitalization.icu_percentage = field
    result = validate_and_score(p, page_texts=pages, source_file="a.pdf")
    assert result.hospitalization.icu_percentage.value is None
    assert result.hospitalization.icu_percentage.normalized_value is None
    assert result.validation.fields_requiring_review == 1


def test_conflict_is_not_resurrected_from_raw_text():
    p = policy(insurer=claim(raw_text="ICU 2%", conflicts=["Conflicting clauses"]))
    out = validate_and_score(p, page_texts={1: "ICU 2%"}, source_file="a.pdf")
    assert out.insurer.value is None and out.insurer.normalized_value is None
    assert out.insurer.status == "conflict"
    assert out.validation.conflict_count == 1


def test_status_without_value_still_needs_evidence():
    p = policy(tpa=FieldValue(status="not_covered"))
    out = validate_and_score(p, page_texts={1: "No tpa information"}, source_file="a.pdf")
    assert out.tpa.status == "unknown"
    assert out.validation.evidence_coverage == 0


def test_empty_extraction_has_zero_evidence_coverage():
    assert (
        validate_and_score(
            policy(), page_texts={}, source_file="a.pdf"
        ).validation.evidence_coverage
        == 0
    )


def test_generic_premium_never_fills_history():
    chunks = [{"text": "Premium: Rs. 90,000", "page_number": 1, "source_file": "a.pdf"}]
    assert mine_field_from_evidence("previous_inception_premium", chunks).value is None


def test_maternity_general_limit_never_fills_metro():
    chunks = [
        {
            "text": "Maximum Limit for Maternity claims is Rs. 50,000 for Normal",
            "page_number": 1,
            "source_file": "a.pdf",
        }
    ]
    assert mine_field_from_evidence("normal_delivery_metro_limit", chunks).value is None


def test_heading_does_not_mean_covered():
    chunks = [{"text": "9 month waiting period", "page_number": 1, "source_file": "a.pdf"}]
    assert mine_field_from_evidence("nine_month_waiting_period_status", chunks).value is None


def pdf_bytes():
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Insurer: Example Insurance\nPolicy Number: XY123\nICU 2%")
    return doc.tobytes()


def test_delete_cleans_all_records_and_source(client, tmp_settings):
    data = pdf_bytes()
    result = client.post(
        "/api/documents/upload", files={"files": ("policy.pdf", data, "application/pdf")}
    )
    doc = result.json()["documents"][0]
    assert client.delete("/api/documents/" + doc["id"]).status_code == 200
    with Session(get_engine(tmp_settings)) as session:
        for model in [
            DocumentPage,
            DocumentChunk,
            ExtractionResult,
            ValidationResult,
            ProcessingJob,
        ]:
            assert not session.exec(select(model).where(model.document_id == doc["id"])).all()
        assert (
            session.execute(
                text("SELECT count(*) FROM chunk_fts WHERE document_id=:id"), {"id": doc["id"]}
            ).scalar()
            == 0
        )
    assert not (tmp_settings.documents_dir / (doc["content_hash"] + ".pdf")).exists()
    assert client.get("/api/policies/" + doc["id"] + "/json").status_code == 404


def test_batch_rejection_leaves_no_stranded_upload(client):
    response = client.post(
        "/api/documents/upload",
        files=[
            ("files", ("valid.pdf", pdf_bytes(), "application/pdf")),
            ("files", ("bad.pdf", b"not a pdf", "application/pdf")),
        ],
    )
    assert response.status_code == 400
    assert not client.get("/api/documents").json()["documents"]


def test_reprocess_invalidates_prior_answers(client):
    doc = client.post(
        "/api/documents/upload", files={"files": ("p.pdf", pdf_bytes(), "application/pdf")}
    ).json()["documents"][0]
    assert client.get("/api/policies/" + doc["id"] + "/json").status_code == 200
    assert client.post("/api/documents/" + doc["id"] + "/reprocess").status_code == 200
    assert client.get("/api/policies/" + doc["id"] + "/json").status_code == 404


@pytest.mark.asyncio
async def test_two_local_store_instances_do_not_lose_other_document(tmp_path: Path):
    a = LocalVectorStore(tmp_path, dimension=2)
    b = LocalVectorStore(tmp_path, dimension=2)

    def chunk(id):
        return Chunk(
            chunk_id=id,
            document_id=id,
            source_file="a.pdf",
            page_number=1,
            section="general",
            text=id,
            embedding=[1, 0],
            text_hash=id,
        )

    await a.upsert_chunks([chunk("one")])
    await b.upsert_chunks([chunk("two")])
    assert len(await a.search("query", query_embedding=[1, 0])) == 2
    await a.delete_document("one")
    assert len(await b.search("query", query_embedding=[1, 0])) == 1


@pytest.mark.asyncio
async def test_extraction_exception_finishes_job(tmp_settings):
    with Session(get_engine(tmp_settings)) as session:
        pipe = PipelineService(tmp_settings, session)
        doc = pipe.save_upload(pdf_bytes(), "p.pdf")
        await pipe.process_document(doc.id)
        pipe.graph_store.upsert_policy = AsyncMock(side_effect=RuntimeError("graph down"))
        # A secondary graph failure must not destroy the authoritative result.
        out = await pipe.extract_policy(doc.id)
        assert out.extraction_metadata.neo4j_sync_status == "error"
        assert session.exec(
            select(ExtractionResult).where(ExtractionResult.document_id == doc.id)
        ).first()


def test_production_requires_authentication(tmp_settings, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import create_app

    tmp_settings.app_env = "production"
    tmp_settings.require_basic_auth = True
    tmp_settings.demo_password = None
    with pytest.raises(RuntimeError, match="DEMO_PASSWORD"), TestClient(create_app()):
        pass


def test_basic_auth_protects_documents(tmp_settings):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from app.main import create_app

    tmp_settings.require_basic_auth = True
    tmp_settings.demo_password = SecretStr("test-only-review-password")
    with TestClient(create_app()) as api:
        assert api.get("/api/health").status_code == 200
        assert api.get("/api/documents").status_code == 401
        assert api.get("/api/documents", auth=("reviewer", "wrong")).status_code == 401
        assert (
            api.get("/api/documents", auth=("reviewer", "test-only-review-password")).status_code
            == 200
        )


def test_empty_search_rejected(client):
    assert client.post("/api/search", json={"query": ""}).status_code == 422


def test_room_schedule_does_not_confuse_si_and_cap():
    text = "Sum Insured Maximum eligibility for Normal Hospitalization Maximum eligibility for ICU Hospitalization\nRs. 700,000 1.5 % of Sum Insured per day 3 % of Sum Insured per day\nRs. 900,000 1.5 % of Sum Insured per day 3 % of Sum Insured per day\nDay Care"
    result = apply_schema_rules(policy(), {1: text})
    result = validate_and_score(result, page_texts={1: text}, source_file="a.pdf")
    assert result.policy_structure.sum_insured_tiers.normalized_value == [700000, 900000]
    assert result.hospitalization.room_rent_percentage.normalized_value == 1.5
    assert result.hospitalization.icu_percentage.normalized_value == 3
    assert result.hospitalization.room_rent_monetary_maximum.value is None


def test_explicit_unlimited_room_keeps_no_limit():
    text = "Sum Insured Normal Hospitalization ICU Hospitalization\nRs. 750,000 No Limit No Limit\nDay Care"
    result = apply_schema_rules(policy(), {1: text})
    assert result.hospitalization.room_rent_monetary_maximum.value == "No Limit"
    assert result.hospitalization.icu_percentage.value is None


def test_different_si_tiers_preserve_their_percentages():
    text = "Sum Insured Normal Hospitalization ICU Hospitalization\nRs. 400,000 1 % of Sum Insured per day 2 % of Sum Insured per day\nRs. 600,000 2 % of Sum Insured per day 4 % of Sum Insured per day"
    result = apply_schema_rules(policy(), {1: text})
    assert result.hospitalization.room_rent_percentage.value == [
        {"sum_insured": 400000, "percentage": 1},
        {"sum_insured": 600000, "percentage": 2},
    ]


def test_current_dates_do_not_become_history_and_real_history_survives():
    p = policy()
    p.previous_policy.policy_period_start = claim("Current policy period: 01-Apr-2023")
    p.previous_policy.previous_inception_premium = claim("Previous year premium: INR 80000")
    result = apply_schema_rules(p, {})
    assert result.previous_policy.policy_period_start.value is None
    assert result.previous_policy.previous_inception_premium.value is not None


def test_premium_table_uses_net_and_total_columns():
    text = "Premium CGST IGST SGST UGST Total Premium\n`100000 `0 `18000 `0 `0 `118000"
    result = apply_schema_rules(policy(), {1: text})
    result = validate_and_score(result, page_texts={1: text}, source_file="a.pdf")
    assert result.current_policy.net_premium.value == 100000
    assert result.current_policy.gross_premium.value == 118000


def test_punctuation_search_is_safe(tmp_settings):
    with Session(get_engine(tmp_settings)) as session:
        assert lexical_search(session, query="???") == []


def test_inconsistent_labeled_premiums_are_a_conflict():
    pages = {1: "Gross premium (Rs.) 140000", 2: "Gross Premium(Rs.) Rs.1,45,000/-"}
    result = apply_schema_rules(policy(), pages)
    result = validate_and_score(result, page_texts=pages, source_file="a.pdf")
    assert result.current_policy.gross_premium.status == "conflict"
    assert result.current_policy.gross_premium.normalized_value is None
    assert len(result.current_policy.gross_premium.evidence) == 2
