from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import text
from sqlmodel import Session, select

from app.db.models import DocumentChunk
from app.providers.embeddings.provider import EmbeddingProvider
from app.providers.vector_store.base import RetrievedChunk

ALIASES: dict[str, list[str]] = {
    "pre-existing disease": ["ped", "existing illness", "pre existing", "pre-existing"],
    "room rent": ["accommodation limit", "room charges", "room & board"],
    "icu": ["intensive care unit", "icu charges", "icu limit"],
    "maternity": [
        "childbirth benefit",
        "maternity benefit",
        "maternity expenses",
        "delivery charges",
        "caesarean",
        "c-section",
        "new born",
        "newborn",
        "baby cover",
    ],
    "waiting period": [
        "initial waiting",
        "30 day",
        "thirty day",
        "first year exclusion",
        "second year exclusion",
        "waiting periods",
    ],
    "ambulance": ["road ambulance", "ambulance charges", "emergency ambulance"],
    "corporate buffer": ["group buffer", "buffer amount", "corporate floater"],
}

FIELD_GROUP_QUERIES: dict[str, str] = {
    "identity": "insurer insurance company TPA policy number insured group company",
    "previous_policy": "previous year prior expiring inception renewal premium tenure",
    "current_policy": "policy period commencement expiry inception net gross premium sum insured",
    "policy_structure": "family definition employee spouse children parents sum insured",
    "demographics": "number of employees spouses children parents lives covered",
    "room_hospitalization": "room rent ICU intensive care pre hospitalization post hospitalization",
    "maternity": (
        "maternity benefit waiting period nine month 9 month baby day one newborn "
        "vaccination normal delivery caesarean c-section metro non-metro childbirth "
        "maternity limit maternity exclusion"
    ),
    "waiting_periods": (
        "waiting period 30 day thirty days initial waiting first year second year "
        "PED pre-existing disease pre existing illness waived applied not covered"
    ),
    "other_benefits": (
        "day care OPD teleconsultation pharmacy domiciliary health check AYUSH organ donor "
        "psychiatric bariatric modern treatment LGBTQ live-in"
    ),
    "infertility_ambulance": "infertility surrogacy ambulance air ambulance",
    "buffer_waivers": "corporate buffer disease wise capping waiver",
}

# Groups that benefit from a larger retrieval budget
BOOSTED_TOP_K_GROUPS = frozenset({"maternity", "waiting_periods", "other_benefits"})


def expand_query(query: str) -> str:
    parts = [query]
    lower = query.lower()
    for canonical, alts in ALIASES.items():
        if canonical in lower or any(a in lower for a in alts):
            parts.extend([canonical, *alts])
    return " ".join(dict.fromkeys(parts))


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", query)
    return " OR ".join(list(dict.fromkeys(tokens))[:80]) if tokens else ""


def lexical_search(
    session: Session,
    *,
    query: str,
    document_id: str | None = None,
    section: str | None = None,
    top_k: int = 8,
) -> list[RetrievedChunk]:
    fts = _fts_query(expand_query(query))
    if not fts:
        return []
    sql = """
        SELECT chunk_id, document_id, section, page_number, text,
               bm25(chunk_fts) AS rank
        FROM chunk_fts
        WHERE chunk_fts MATCH :q
    """
    params: dict = {"q": fts}
    if document_id:
        sql += " AND document_id = :document_id"
        params["document_id"] = document_id
    if section:
        sql += " AND section = :section"
        params["section"] = section
    sql += " ORDER BY rank LIMIT :top_k"
    params["top_k"] = top_k
    result = session.execute(text(sql), params)
    rows = result.fetchall()
    out: list[RetrievedChunk] = []
    for row in rows:
        chunk = session.exec(
            select(DocumentChunk).where(DocumentChunk.chunk_id == row.chunk_id)
        ).first()
        source_file = ""
        parser = "text"
        chunk_type = "text"
        text_hash = ""
        body = row.text
        if chunk:
            source_file = ""  # filled by caller if needed
            parser = chunk.parser
            chunk_type = chunk.chunk_type
            text_hash = chunk.text_hash
            body = chunk.text
            # recover source from chunk_id pattern not needed
        # rank is lower-better for bm25 in sqlite; invert
        score = -float(row.rank)
        out.append(
            RetrievedChunk(
                chunk_id=row.chunk_id,
                document_id=row.document_id,
                source_file=source_file,
                page_number=int(row.page_number),
                section=row.section,
                text=body,
                score=score,
                chunk_type=chunk_type,
                parser=parser,
                text_hash=text_hash,
            )
        )
    return out


def normalize_scores(chunks: Iterable[RetrievedChunk]) -> list[RetrievedChunk]:
    items = list(chunks)
    if not items:
        return []
    vals = [c.score for c in items]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    for c in items:
        c.score = (c.score - lo) / span
    return items


async def hybrid_search(
    session: Session,
    vector_store,
    embedder: EmbeddingProvider,
    *,
    query: str,
    document_id: str | None = None,
    section: str | None = None,
    top_k: int = 8,
    source_file: str = "",
) -> list[RetrievedChunk]:
    expanded = expand_query(query)
    lexical = lexical_search(
        session, query=expanded, document_id=document_id, section=section, top_k=top_k
    )
    q_emb = embedder.embed([expanded])[0]
    semantic = await vector_store.search(
        expanded,
        document_id=document_id,
        section=section,
        top_k=top_k,
        query_embedding=q_emb,
    )
    # Prefer full SQLite chunk text over vector-store metadata previews.
    for item in semantic:
        row = session.exec(
            select(DocumentChunk).where(DocumentChunk.chunk_id == item.chunk_id)
        ).first()
        if row:
            item.text = row.text
            item.parser = row.parser
            item.chunk_type = row.chunk_type
            if not item.section:
                item.section = row.section or item.section
        if source_file and not item.source_file:
            item.source_file = source_file

    for item in lexical:
        if source_file and not item.source_file:
            item.source_file = source_file

    # Reciprocal rank fusion preserves each retriever's ordering, including equal scores.
    # Keep the fuller text when both lexical and semantic hit the same chunk.
    merged: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    for result_set, weight in ((lexical, 0.6), (semantic, 0.4)):
        for rank, chunk in enumerate(result_set, 1):
            if document_id and chunk.document_id != document_id:
                continue
            existing = merged.get(chunk.chunk_id)
            if existing is None or len(chunk.text or "") > len(existing.text or ""):
                merged[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0) + weight / (60 + rank)
    ranked = sorted(merged.values(), key=lambda c: scores[c.chunk_id], reverse=True)
    for chunk in ranked:
        chunk.score = scores[chunk.chunk_id]
    return ranked[:top_k]
