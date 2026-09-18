from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    frontend_url: str = "http://localhost:5173"
    allowed_origins: str = "http://localhost:5173"

    data_dir: Path = Path("./data")
    output_dir: Path = Path("./outputs")
    database_url: str = "sqlite:///./data/policylens.db"

    llm_provider: Literal["mock", "openai", "gemini", "groq", "auto"] = "mock"
    llm_model: str = ""
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: SecretStr | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"

    embedding_provider: Literal["local", "hash", "huggingface"] = "hash"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hf_token: SecretStr | None = None
    huggingface_api_url: str = "https://router.huggingface.co/hf-inference"

    vector_store: Literal["pinecone", "local"] = "local"
    vector_namespace: str = "policylens-development"
    pinecone_api_key: SecretStr | None = None
    pinecone_index_name: str = "policylens"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"
    pinecone_dimension: int = 384

    graph_store: Literal["neo4j", "local"] = "local"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr | None = None
    neo4j_database: str = "neo4j"

    ocr_enabled: bool = True
    ocr_language: str = "eng"
    ocr_min_text_chars: int = 40

    top_k: int = 8
    rerank_enabled: bool = False
    max_upload_mb: int = 50
    max_pdf_pages: int = 200
    max_batch_files: int = 10
    llm_timeout_seconds: int = 90
    llm_max_attempts: int = 5
    demo_username: str = "reviewer"
    demo_password: SecretStr | None = None
    require_basic_auth: bool = False
    serve_frontend: bool = False
    auto_seed_samples: bool = True

    @field_validator("data_dir", "output_dir", mode="before")
    @classmethod
    def _as_path(cls, value: str | Path) -> Path:
        return Path(value)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def documents_dir(self) -> Path:
        return self.data_dir / "documents"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    @property
    def vector_store_dir(self) -> Path:
        return self.data_dir / "vector_store"

    @property
    def graph_store_dir(self) -> Path:
        return self.data_dir / "graph_store"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def ensure_dirs(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        if not self.data_dir.is_absolute():
            self.data_dir = (repo_root / self.data_dir).resolve()
        if not self.output_dir.is_absolute():
            self.output_dir = (repo_root / self.output_dir).resolve()
        if self.database_url.startswith("sqlite:///./"):
            rel = self.database_url.removeprefix("sqlite:///./")
            self.database_url = f"sqlite:///{(repo_root / rel).resolve()}"
        for path in (
            self.data_dir,
            self.documents_dir,
            self.pages_dir,
            self.vector_store_dir,
            self.graph_store_dir,
            self.output_dir / "sample",
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
