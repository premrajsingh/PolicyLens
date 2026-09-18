from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)


class EmbeddingProvider(Protocol):
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def healthcheck(self) -> dict: ...


class HashEmbeddingProvider:
    """Deterministic local embeddings for tests/offline without heavyweight models."""

    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        vec = [0.0] * self.dimension
        if not tokens:
            return vec
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(0, min(len(digest), 32)):
                idx = (digest[i] + i * 17) % self.dimension
                vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def healthcheck(self) -> dict:
        return {"name": "hash_embeddings", "status": "ok", "dimension": self.dimension}


class LocalSentenceTransformerProvider:
    def __init__(self, model_name: str, dimension: int) -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.model = SentenceTransformer(model_name)
        self.dimension = dimension
        probe = self.model.encode(["dimension check"], normalize_embeddings=True)
        actual = len(probe[0])
        if actual != dimension:
            raise ValueError(
                f"Embedding model dimension {actual} != configured PINECONE_DIMENSION={dimension}"
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def healthcheck(self) -> dict:
        return {
            "name": "sentence_transformers",
            "status": "ok",
            "model": self.model_name,
            "dimension": self.dimension,
        }


def _mean_pool(matrix: list[list[float]]) -> list[float]:
    if not matrix:
        return []
    dim = len(matrix[0])
    acc = [0.0] * dim
    for row in matrix:
        for i, v in enumerate(row):
            acc[i] += float(v)
    n = float(len(matrix))
    return [v / n for v in acc]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _is_number_list(payload: object) -> bool:
    return isinstance(payload, list) and bool(payload) and isinstance(payload[0], (int, float))


def _coerce_embedding(payload: object) -> list[float]:
    """Normalize HF Inference responses to a single embedding vector."""
    if _is_number_list(payload):
        return [float(x) for x in payload]  # type: ignore[arg-type]
    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        # [[float, ...]] → one vector OR token matrix
        if _is_number_list(payload[0]):
            # Ambiguous: either one sentence embedding wrapped in a list,
            # or token-level matrix. Prefer sentence embedding when outer
            # length is 1; otherwise mean-pool tokens.
            if len(payload) == 1:
                return [float(x) for x in payload[0]]  # type: ignore[arg-type]
            return _mean_pool(payload)  # type: ignore[arg-type]
        # batch of vectors / nested → first item
        return _coerce_embedding(payload[0])
    raise ValueError(f"Unexpected Hugging Face embedding payload type: {type(payload)}")


def _coerce_batch(payload: object, expected: int) -> list[list[float]]:
    """Normalize a batch HF response into expected number of vectors."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("Empty Hugging Face embedding batch")

    # Batch of sentence vectors: [[f...], [f...], ...]
    if all(isinstance(row, list) and row and isinstance(row[0], (int, float)) for row in payload):
        if len(payload) == expected:
            return [_l2_normalize([float(x) for x in row]) for row in payload]  # type: ignore[arg-type]
        # Single sentence returned as token matrix when expected==1
        if expected == 1:
            return [_l2_normalize(_coerce_embedding(payload))]

    # Batch of token matrices: [[[f...], ...], ...]
    if all(isinstance(row, list) for row in payload) and len(payload) == expected:
        return [_l2_normalize(_coerce_embedding(row)) for row in payload]

    if expected == 1:
        return [_l2_normalize(_coerce_embedding(payload))]

    raise ValueError(
        f"HF batch size mismatch: got type={type(payload)} len="
        f"{len(payload) if isinstance(payload, list) else 'n/a'} expected={expected}"
    )


class HuggingFaceEmbeddingProvider:
    """Hugging Face Inference API embeddings — no silent fallback to hash."""

    def __init__(
        self,
        *,
        token: str,
        model_name: str,
        dimension: int,
        api_url: str = "https://router.huggingface.co/hf-inference",
    ) -> None:
        if not token:
            raise ValueError(
                "EMBEDDING_PROVIDER=huggingface requires HF_TOKEN; refusing silent fallback to hash"
            )
        self.token = token
        self.model_name = model_name
        self.dimension = dimension
        self.api_url = api_url.rstrip("/")
        self._batch_size = 16

    def _endpoints(self) -> list[str]:
        model = self.model_name
        return [
            f"{self.api_url}/models/{model}/pipeline/feature-extraction",
            f"{self.api_url}/pipeline/feature-extraction/{model}",
            f"{self.api_url}/models/{model}",
            f"https://api-inference.huggingface.co/pipeline/feature-extraction/{model}",
            f"https://api-inference.huggingface.co/models/{model}",
        ]

    def _post(self, texts: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        # HF feature-extraction expects a list of strings for sentence embeddings.
        body = {"inputs": texts, "options": {"wait_for_model": True}}
        last_error: Exception | None = None
        with httpx.Client(timeout=120.0, trust_env=False) as client:
            for url in self._endpoints():
                try:
                    resp = client.post(url, headers=headers, json=body)
                    if resp.status_code == 404:
                        continue
                    if resp.status_code == 403:
                        detail = resp.text[:240]
                        raise PermissionError(
                            "HF_TOKEN lacks Inference Providers permission "
                            "(need fine-grained: Make calls to Inference Providers). "
                            f"Detail: {detail}"
                        )
                    resp.raise_for_status()
                    vectors = _coerce_batch(resp.json(), expected=len(texts))
                    for vec in vectors:
                        if len(vec) != self.dimension:
                            raise ValueError(
                                f"HF embedding dim {len(vec)} != "
                                f"PINECONE_DIMENSION={self.dimension}"
                            )
                    return vectors
                except PermissionError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.warning("hf_embed_endpoint_failed url=%s error=%s", url, str(exc)[:200])
                    continue
        raise RuntimeError(f"Hugging Face embedding failed: {last_error}")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            # Truncate extremely long chunks to keep Inference payload sane
            clipped = [t[:8000] if len(t) > 8000 else t for t in batch]
            out.extend(self._post(clipped))
        return out

    def healthcheck(self) -> dict:
        try:
            probe = self.embed(["policylens healthcheck"])
            return {
                "name": "huggingface_embeddings",
                "status": "ok",
                "model": self.model_name,
                "dimension": len(probe[0]) if probe else self.dimension,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "name": "huggingface_embeddings",
                "status": "error",
                "detail": str(exc)[:300],
                "model": self.model_name,
                "dimension": self.dimension,
            }


def create_embedding_provider(settings) -> EmbeddingProvider:
    if settings.embedding_provider == "hash":
        return HashEmbeddingProvider(dimension=settings.pinecone_dimension)
    if settings.embedding_provider == "local":
        return LocalSentenceTransformerProvider(
            settings.embedding_model, settings.pinecone_dimension
        )
    if settings.embedding_provider == "huggingface":
        token = settings.hf_token.get_secret_value() if settings.hf_token else ""
        if not token:
            raise ValueError(
                "EMBEDDING_PROVIDER=huggingface requires HF_TOKEN; refusing silent fallback to hash"
            )
        return HuggingFaceEmbeddingProvider(
            token=token,
            model_name=settings.embedding_model,
            dimension=settings.pinecone_dimension,
            api_url=settings.huggingface_api_url,
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER={settings.embedding_provider}")
