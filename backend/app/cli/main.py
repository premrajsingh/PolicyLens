from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

from sqlmodel import Session, select

from app.config import get_settings
from app.core.logging import setup_logging
from app.core.security import is_ignored_path
from app.db.models import Document, ExtractionResult
from app.db.session import get_engine, init_db
from app.extraction.pipeline import PipelineService
from app.models.schema import ExtractedPolicy


def _session():
    settings = get_settings()
    init_db(settings)
    return Session(get_engine(settings)), settings


async def cmd_ingest(input_dir: Path) -> None:
    session, settings = _session()
    with session:
        pipeline = PipelineService(settings, session)
        for path in sorted(input_dir.rglob("*.pdf")):
            if is_ignored_path(path):
                print(f"skip ignored {path}")
                continue
            doc = pipeline.save_upload(path.read_bytes(), path.name)
            print(f"ingested id={doc.id} status={doc.status} file={doc.filename}")


async def cmd_process(document_id: str) -> None:
    session, settings = _session()
    with session:
        pipeline = PipelineService(settings, session)
        job = await pipeline.process_document(document_id)
        print(json.dumps({"job_id": job.id, "status": job.status, "stage": job.stage}, indent=2))


async def cmd_extract_all(input_dir: Path, output_dir: Path) -> None:
    session, settings = _session()
    with session:
        pipeline = PipelineService(settings, session)
        extracted = {}
        for path in sorted(input_dir.rglob("*.pdf")):
            if is_ignored_path(path):
                continue
            doc = pipeline.save_upload(path.read_bytes(), path.name)
            target_id = (
                doc.duplicate_of if doc.status == "duplicate" and doc.duplicate_of else doc.id
            )
            if doc.status == "duplicate":
                print(f"duplicate {path.name} -> {target_id}")
            target = session.get(Document, target_id)
            if not target:
                continue
            needs_process = target_id not in extracted and target.status not in {
                "processed",
                "extracted",
                "partial",
            }
            # Re-embed + upsert when Pinecone is configured but vectors never landed
            # (common after earlier local runs that falsely set pinecone_status=indexed).
            if (
                target_id not in extracted
                and settings.vector_store == "pinecone"
                and target.pinecone_status != "indexed"
            ):
                needs_process = True
            if needs_process:
                print(
                    f"processing id={target_id} status={target.status} "
                    f"pinecone={target.pinecone_status}"
                )
                await pipeline.process_document(target_id, reprocess=True)
            policy = extracted.get(target_id)
            if policy is None:
                policy = await pipeline.extract_policy(target_id)
                extracted[target_id] = policy
            else:
                policy = policy.model_copy(deep=True)
                policy.extraction_metadata.source_aliases.append(path.name)
            # Write per source filename for demo clarity
            safe = re.sub(r"[^A-Za-z0-9._\-]+", "_", path.stem)[:120]
            output_dir.mkdir(parents=True, exist_ok=True)
            out = output_dir / f"{safe}.json"
            out.write_text(json.dumps(policy.model_dump(mode="json"), indent=2), encoding="utf-8")
            print(f"wrote {out}")


def cmd_validate_output(path: Path) -> None:
    files = [path] if path.is_file() else sorted(path.glob("*.json"))
    ok = 0
    for file_path in files:
        current = file_path
        data = json.loads(current.read_text(encoding="utf-8"))
        ExtractedPolicy.model_validate(data)

        def walk(obj, prefix="", _file=current):
            if isinstance(obj, dict):
                if "evidence" in obj and "status" in obj:
                    if obj.get("value") is not None and not obj.get("evidence"):
                        raise AssertionError(f"{_file}: {prefix} non-null without evidence")
                    return
                for k, v in obj.items():
                    walk(v, f"{prefix}.{k}")

        walk(data)
        ok += 1
        print(f"valid {current}")
    print(f"validated {ok} files")


async def cmd_graph_sync(document_id: str) -> None:
    session, settings = _session()
    with session:
        pipeline = PipelineService(settings, session)
        row = session.exec(
            select(ExtractionResult).where(ExtractionResult.document_id == document_id)
        ).first()
        if not row:
            raise SystemExit("Extraction not found")
        policy = ExtractedPolicy.model_validate(row.payload)
        await pipeline.graph_store.upsert_policy(policy)
        print("graph synced")


async def cmd_healthcheck() -> None:
    session, settings = _session()
    with session:
        pipeline = PipelineService(settings, session)
        print("llm", (await pipeline.llm.healthcheck()).model_dump())
        print("vector", (await pipeline.vector_store.healthcheck()).model_dump())
        print("graph", (await pipeline.graph_store.healthcheck()).model_dump())
        print("embeddings", pipeline.embedder.healthcheck())


def cmd_run_evals() -> None:
    root = Path(__file__).resolve().parents[3]
    script = root / "evals" / "run_evals.py"
    subprocess.check_call([sys.executable, str(script)])


def main(argv: list[str] | None = None) -> None:
    setup_logging()
    parser = argparse.ArgumentParser(prog="policylens")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("--input-dir", type=Path, required=True)

    p_process = sub.add_parser("process")
    p_process.add_argument("--document-id", required=True)

    p_extract = sub.add_parser("extract-all")
    p_extract.add_argument("--input-dir", type=Path, required=True)
    p_extract.add_argument("--output-dir", type=Path, required=True)

    p_val = sub.add_parser("validate-output")
    p_val.add_argument("--path", type=Path, required=True)

    p_graph = sub.add_parser("graph-sync")
    p_graph.add_argument("--document-id", required=True)

    sub.add_parser("run-evals")
    sub.add_parser("healthcheck")

    args = parser.parse_args(argv)
    if args.cmd == "ingest":
        asyncio.run(cmd_ingest(args.input_dir))
    elif args.cmd == "process":
        asyncio.run(cmd_process(args.document_id))
    elif args.cmd == "extract-all":
        asyncio.run(cmd_extract_all(args.input_dir, args.output_dir))
    elif args.cmd == "validate-output":
        cmd_validate_output(args.path)
    elif args.cmd == "graph-sync":
        asyncio.run(cmd_graph_sync(args.document_id))
    elif args.cmd == "run-evals":
        cmd_run_evals()
    elif args.cmd == "healthcheck":
        asyncio.run(cmd_healthcheck())


if __name__ == "__main__":
    main()
