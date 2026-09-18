from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.core.security import is_ignored_path, safe_filename
from app.core.version import PIPELINE_VERSION, SCHEMA_VERSION
from app.db.session import init_db, reset_engine
from app.extraction.normalize import (
    normalize_currency,
    normalize_date,
    normalize_duration,
    normalize_percentage,
    normalize_status,
)
from app.ingestion.pdf import sha256_bytes, should_ocr, validate_upload_bytes
from app.main import create_app
from app.models.schema import (
    DocumentInfo,
    EvidenceItem,
    ExtractedPolicy,
    ExtractionMetadata,
    FieldValue,
    ValidationSummary,
)
from app.providers.embeddings.provider import HashEmbeddingProvider
from app.providers.graph_store.local import LocalGraphStore
from app.providers.llm.provider import MockLLMProvider
from app.providers.vector_store.base import Chunk
from app.providers.vector_store.local import LocalVectorStore
from app.validation.engine import enforce_no_hallucination, validate_and_score


@pytest.fixture()
def tmp_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    reset_engine()
    get_settings.cache_clear()
    db = tmp_path / "test.db"
    settings = Settings(
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "outputs",
        database_url=f"sqlite:///{db}",
        llm_provider="mock",
        vector_store="local",
        graph_store="local",
        embedding_provider="hash",
        ocr_enabled=False,
        max_upload_mb=5,
    )
    settings.ensure_dirs()
    monkeypatch.setenv("DATABASE_URL", settings.database_url)
    monkeypatch.setenv("DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("VECTOR_STORE", "local")
    monkeypatch.setenv("GRAPH_STORE", "local")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    get_settings.cache_clear()
    # Patch get_settings to return our settings
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.main.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes_health.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes_documents.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes_policies.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes_search.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes_comparison.get_settings", lambda: settings)
    reset_engine()
    init_db(settings)
    return settings


@pytest.fixture()
def client(tmp_settings: Settings) -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_macos_filtering():
    assert is_ignored_path("__MACOSX/foo.pdf")
    assert is_ignored_path("._Policy.pdf")
    assert not is_ignored_path("GHI Policy.pdf")
    with pytest.raises(ValueError):
        safe_filename("._hidden.pdf")


def test_hashing_and_upload_validation(tmp_path: Path):
    data = b"%PDF-1.4 minimal"
    h = sha256_bytes(data)
    assert len(h) == 64
    name = validate_upload_bytes(data, "sample.pdf", 1024)
    assert name == "sample.pdf"
    with pytest.raises(ValueError):
        validate_upload_bytes(data, "._x.pdf", 1024)
    with pytest.raises(ValueError):
        validate_upload_bytes(b"notpdf", "a.pdf", 1024)


def test_ocr_decision():
    assert should_ocr("hi", 40) is True
    assert should_ocr("x" * 50, 40) is False


def test_normalizers():
    assert normalize_currency("₹5,00,000") == 500000.0
    assert normalize_currency("Rs. 5,00,000") == 500000.0
    assert normalize_currency("5 lakh") == 500000.0
    assert normalize_percentage("1%") == 1.0
    assert normalize_duration("30 days") == {"value": 30, "unit": "days"}
    assert normalize_duration("thirty days") == {"value": 30, "unit": "days"}
    assert normalize_duration("9 months") == {"value": 9, "unit": "months"}
    assert normalize_date("26/04/2024") == "2024-04-26"
    assert normalize_status("waived off") == "waived_off"
    assert normalize_status("not covered") == "not_covered"
    assert normalize_status("covered from day one") == "covered"


def test_no_hallucination_without_evidence():
    field = FieldValue(value="TATA AIG", status="covered", confidence=0.9, evidence=[])
    field = enforce_no_hallucination(field)
    assert field.value is None
    assert field.status == "unknown"


@pytest.mark.asyncio
async def test_mock_llm_does_not_fabricate():
    llm = MockLLMProvider()
    out = await llm.extract_group(
        group="identity",
        fields=["insurer", "tpa"],
        evidence_chunks=[{"text": "random text", "page_number": 1}],
        source_file="x.pdf",
    )
    assert out["insurer"]["value"] is None
    assert out["insurer"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_local_vector_store(tmp_path: Path):
    store = LocalVectorStore(tmp_path / "vs", dimension=8)
    emb = HashEmbeddingProvider(dimension=8).embed(["room rent 1% of sum insured"])[0]
    await store.upsert_chunks(
        [
            Chunk(
                chunk_id="d1-page-1-chunk-0",
                document_id="d1",
                source_file="a.pdf",
                page_number=1,
                section="room_hospitalization",
                text="room rent 1% of sum insured",
                embedding=emb,
                text_hash="abc",
            )
        ]
    )
    hits = await store.search(
        "room rent",
        document_id="d1",
        top_k=3,
        query_embedding=emb,
    )
    assert hits and hits[0].document_id == "d1"
    # isolation
    hits2 = await store.search("room rent", document_id="other", query_embedding=emb)
    assert hits2 == []
    health = await store.healthcheck()
    assert health.status == "ok"
    await store.delete_document("d1")


@pytest.mark.asyncio
async def test_local_graph_store(tmp_path: Path):
    store = LocalGraphStore(tmp_path / "graph")
    policy = ExtractedPolicy(
        schema_version=SCHEMA_VERSION,
        pipeline_version=PIPELINE_VERSION,
        document=DocumentInfo(
            document_id="p1",
            filename="a.pdf",
            content_hash="h",
            page_count=1,
        ),
        insurer=FieldValue(
            value="Demo Insurer",
            status="covered",
            confidence=0.7,
            evidence=[
                EvidenceItem(source_file="a.pdf", page_number=1, quote="Insurer: Demo Insurer")
            ],
        ),
        extraction_metadata=ExtractionMetadata(
            provider="mock", model="mock", generated_at="2026-01-01T00:00:00Z"
        ),
        validation=ValidationSummary(overall_confidence=0.7, fields_found=1),
    )
    await store.upsert_policy(policy)
    graph = await store.get_policy_graph("p1")
    assert graph["available"] is True
    await store.delete_policy("p1")


def test_pinecone_missing_config(tmp_settings: Settings, monkeypatch: pytest.MonkeyPatch):
    from app.providers.vector_store.factory import create_vector_store

    tmp_settings.vector_store = "pinecone"
    tmp_settings.pinecone_api_key = None
    with pytest.raises(ValueError, match="refusing silent fallback"):
        create_vector_store(tmp_settings)


def test_neo4j_missing_config(tmp_settings: Settings):
    from app.providers.graph_store.factory import create_graph_store

    tmp_settings.graph_store = "neo4j"
    tmp_settings.neo4j_password = None
    with pytest.raises(ValueError, match="refusing silent fallback"):
        create_graph_store(tmp_settings)


def test_groq_missing_config(tmp_settings: Settings):
    from app.providers.llm.provider import create_llm_provider

    tmp_settings.llm_provider = "groq"
    tmp_settings.groq_api_key = None
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        create_llm_provider(tmp_settings)


def test_huggingface_missing_config(tmp_settings: Settings):
    from app.providers.embeddings.provider import create_embedding_provider

    tmp_settings.embedding_provider = "huggingface"
    tmp_settings.hf_token = None
    with pytest.raises(ValueError, match="HF_TOKEN"):
        create_embedding_provider(tmp_settings)


def test_health_endpoints(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    r2 = client.get("/api/providers/health")
    assert r2.status_code == 200
    assert "providers" in r2.json()
    assert "X-Request-ID" in r.headers


def test_upload_and_duplicate(client: TestClient, tmp_settings: Settings):
    # Minimal PDF bytes
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Insurer: Example Insurance\nPolicy Number: ABC-123\nRoom rent: 1%")
    data = doc.tobytes()
    doc.close()

    files = [("files", ("policy.pdf", data, "application/pdf"))]
    r = client.post("/api/documents/upload", files=files)
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert docs[0]["status"] == "uploaded"
    doc_id = docs[0]["id"]

    r2 = client.post("/api/documents/upload", files=files)
    assert r2.json()["documents"][0]["status"] == "duplicate"

    r3 = client.post(f"/api/documents/{doc_id}/process")
    assert r3.status_code == 200
    assert r3.json()["status"] == "completed"

    r4 = client.post(f"/api/policies/{doc_id}/extract")
    assert r4.status_code == 200
    payload = r4.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    # non-null fields must have evidence
    insurer = payload["insurer"]
    if insurer.get("value") is not None:
        assert insurer.get("evidence")

    r5 = client.get(f"/api/policies/{doc_id}/json")
    assert r5.status_code == 200
    r6 = client.get(f"/api/policies/{doc_id}/evidence")
    assert r6.status_code == 200
    r7 = client.get(f"/api/policies/{doc_id}/validation")
    assert r7.status_code == 200
    r8 = client.get(f"/api/policies/{doc_id}/graph")
    assert r8.status_code == 200

    r9 = client.post(
        "/api/search",
        json={"query": "room rent", "document_id": doc_id, "top_k": 5},
    )
    assert r9.status_code == 200


def test_validate_and_score_clears_bad_evidence():
    policy = ExtractedPolicy(
        schema_version=SCHEMA_VERSION,
        pipeline_version=PIPELINE_VERSION,
        document=DocumentInfo(document_id="d", filename="a.pdf", content_hash="h"),
        insurer=FieldValue(
            value="X",
            status="covered",
            evidence=[EvidenceItem(source_file="a.pdf", page_number=1, quote="not in page")],
        ),
        extraction_metadata=ExtractionMetadata(provider="mock", model="m", generated_at="t"),
    )
    out = validate_and_score(policy, page_texts={1: "Insurer: Example"}, source_file="a.pdf")
    assert out.insurer.value is None
    assert out.insurer.status == "unknown"


def test_validate_keeps_short_icu_quote():
    """Short quotes like 'ICU 2%' must not wipe a real extracted value."""
    from app.models.schema import Hospitalization

    policy = ExtractedPolicy(
        schema_version=SCHEMA_VERSION,
        pipeline_version=PIPELINE_VERSION,
        document=DocumentInfo(document_id="d", filename="a.pdf", content_hash="h"),
        hospitalization=Hospitalization(
            icu_percentage=FieldValue(
                value="2%",
                normalized_value=2.0,
                status="covered",
                raw_text="ICU 2%",
                confidence=0.9,
                evidence=[
                    EvidenceItem(source_file="a.pdf", page_number=1, quote="ICU 2%"),
                ],
            )
        ),
        extraction_metadata=ExtractionMetadata(provider="mock", model="m", generated_at="t"),
    )
    out = validate_and_score(
        policy,
        page_texts={1: "Room rent: 1% | ICU 2% | Pre hospitalization 30 days"},
        source_file="a.pdf",
    )
    assert out.hospitalization.icu_percentage.value == "2%"
    assert out.hospitalization.icu_percentage.status != "unknown"


def test_mine_maternity_waiting_patterns():
    from app.extraction.fields import mine_field_from_evidence

    chunks = [
        {
            "text": "Maternity: 9 month waiting period waived. Baby day one cover available. "
            "30 day waiting period applied. PED waiting period waived off.",
            "page_number": 2,
            "section": "maternity",
            "parser": "text",
            "source_file": "p.pdf",
            "score": 0.9,
        }
    ]
    nine = mine_field_from_evidence("nine_month_waiting_period_status", chunks)
    assert nine.value is not None
    assert nine.evidence
    baby = mine_field_from_evidence("baby_day_one_cover", chunks)
    assert baby.value is not None
    thirty = mine_field_from_evidence("initial_30_day_status", chunks)
    assert thirty.value is not None
    ped = mine_field_from_evidence("ped_waiting_period_status", chunks)
    assert ped.value is not None
