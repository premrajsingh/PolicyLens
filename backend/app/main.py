from __future__ import annotations

import base64
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from app.api import (
    routes_comparison,
    routes_documents,
    routes_health,
    routes_policies,
    routes_search,
)
from app.config import get_settings
from app.core.errors import AppError, app_error_handler, http_error_handler, unhandled_error_handler
from app.core.logging import new_request_id, request_id_ctx, setup_logging
from app.db.models import Document, ProcessingJob, utcnow
from app.db.session import get_engine, init_db


from app.providers.graph_store.factory import close_graph_store


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging()
    settings.ensure_dirs()
    if settings.app_env == "production" and settings.require_basic_auth and not settings.demo_password:
        raise RuntimeError("Set DEMO_PASSWORD when REQUIRE_BASIC_AUTH=true")
    init_db(settings)
    # Background tasks do not survive a restart. Surface interrupted work honestly.
    with Session(get_engine(settings)) as session:
        for job in session.exec(
            select(ProcessingJob).where(ProcessingJob.status == "running")
        ).all():
            job.status = "failed"
            job.error_message = "Interrupted by server restart. Retry extraction."
            job.finished_at = utcnow()
            session.add(job)
        for doc in session.exec(
            select(Document).where(Document.status.in_(["processing", "queued"]))
        ).all():
            doc.status = "error"
            doc.error_message = "Interrupted by server restart. Retry extraction."
            session.add(doc)
        session.commit()
    yield
    await close_graph_store()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PolicyLens",
        version="0.2.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        if (
            settings.require_basic_auth
            and settings.demo_password
            and request.url.path != "/api/health"
            and request.method != "OPTIONS"
        ):
            try:
                scheme, encoded = request.headers.get("Authorization", "").split(" ", 1)
                user, password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
                allowed = (
                    scheme.lower() == "basic"
                    and secrets.compare_digest(user.encode(), settings.demo_username.encode())
                    and secrets.compare_digest(
                        password.encode(), settings.demo_password.get_secret_value().encode()
                    )
                )
            except (ValueError, UnicodeError):
                allowed = False
            if not allowed:
                return JSONResponse(
                    {
                        "error": {
                            "code": "unauthorized",
                            "message": "Sign in to the policy workspace.",
                        }
                    },
                    status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="PolicyLens", charset="UTF-8"'},
                )
        rid = new_request_id()
        token = request_id_ctx.set(rid)
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            request_id_ctx.reset(token)

    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(HTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)

    app.include_router(routes_health.router)
    app.include_router(routes_documents.router)
    app.include_router(routes_policies.router)
    app.include_router(routes_search.router)
    app.include_router(routes_comparison.router)
    if settings.serve_frontend:
        frontend = Path(__file__).resolve().parents[1] / "static"
        if not frontend.exists():
            frontend = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        if (frontend / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend_page(path: str):
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found")
            candidate = (frontend / path).resolve()
            if candidate.is_relative_to(frontend.resolve()) and candidate.is_file():
                return FileResponse(candidate)
            if not (frontend / "index.html").is_file():
                raise HTTPException(status_code=503, detail="Build the frontend first")
            return FileResponse(frontend / "index.html")

    return app


app = create_app()
