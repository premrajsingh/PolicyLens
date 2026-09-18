from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from app.extraction.instructions import GROUP_INSTRUCTIONS, SYSTEM_PROMPT
from app.models.schema import FieldValue, HealthStatus, unknown_field

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    name: str
    model: str | None

    async def extract_group(
        self,
        *,
        group: str,
        fields: list[str],
        evidence_chunks: list[dict[str, Any]],
        source_file: str,
    ) -> dict[str, Any]: ...

    async def healthcheck(self) -> HealthStatus: ...


class MockLLMProvider:
    """Test/offline provider. Never fabricates policy values."""

    name = "mock"
    model = "mock-deterministic"

    async def extract_group(
        self,
        *,
        group: str,
        fields: list[str],
        evidence_chunks: list[dict[str, Any]],
        source_file: str,
    ) -> dict[str, Any]:
        # Deterministic heuristic: only fill when evidence clearly contains field keywords
        # and a nearby value pattern — still requires validation/evidence checks downstream.
        result: dict[str, Any] = {}
        joined = "\n".join(c.get("text", "") for c in evidence_chunks)
        for field in fields:
            fv = unknown_field().model_dump()
            # Mock never invents insurer/premium/limits from knowledge — only unknown unless
            # explicit extractable patterns are present in evidence text for identity-like fields.
            if group == "identity" and field in {"insurer", "tpa"} and evidence_chunks:
                # Leave unknown; OpenAI/Gemini required for richer extraction.
                pass
            result[field] = fv
        _ = joined, source_file
        return result

    async def healthcheck(self) -> HealthStatus:
        return HealthStatus(
            name="llm_mock",
            status="ok",
            detail="Deterministic mock — does not fabricate policy values",
            configured=True,
        )


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        provider_name: str = "openai",
        timeout: float = 40,
        max_attempts: int = 2,
        missing_key_message: str = "OPENAI_API_KEY is required when LLM_PROVIDER=openai",
    ) -> None:
        if not api_key:
            raise ValueError(missing_key_message)
        from openai import AsyncOpenAI

        self.name = provider_name
        self.model = model or "gpt-4o-mini"
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0
        )
        self.max_attempts = max_attempts

    async def extract_group(
        self,
        *,
        group: str,
        fields: list[str],
        evidence_chunks: list[dict[str, Any]],
        source_file: str,
    ) -> dict[str, Any]:
        import asyncio

        from openai import APIStatusError, RateLimitError

        system = SYSTEM_PROMPT + "\n" + GROUP_INSTRUCTIONS.get(group, "")
        # Keep prompts tiny so free-tier TPD survives a full multi-doc demo.
        slim_chunks: list[dict[str, Any]] = []
        for chunk in evidence_chunks[:6]:
            text = str(chunk.get("text") or "")[:450]
            slim_chunks.append(
                {
                    "page_number": chunk.get("page_number"),
                    "section": chunk.get("section"),
                    "text": text,
                }
            )
        user = {
            "group": group,
            "fields": fields,
            "source_file": source_file,
            "evidence_chunks": slim_chunks,
        }
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    temperature=0,
                    max_completion_tokens=1200,
                    **({"reasoning_effort": "low"} if "gpt-oss" in self.model else {}),
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": json.dumps(user)},
                    ],
                )
                if response.choices[0].finish_reason not in {"stop", None}:
                    raise ValueError("LLM response was incomplete")
                content = response.choices[0].message.content or "{}"
                payload = json.loads(content)
                if not isinstance(payload, dict) or not all(k in payload for k in fields):
                    raise ValueError("LLM response is missing requested fields")
                return payload
            except (RateLimitError, APIStatusError) as exc:
                last_error = exc
                status = getattr(exc, "status_code", None) or getattr(
                    getattr(exc, "response", None), "status_code", None
                )
                if status not in {429, 503} and not isinstance(exc, RateLimitError):
                    raise
                if attempt + 1 == self.max_attempts:
                    break
                retry_after = (
                    exc.response.headers.get("retry-after", "")
                    if getattr(exc, "response", None)
                    else ""
                )
                try:
                    # Wait through short rate limits; cap long waits so demos can recover.
                    wait = min(max(float(retry_after), 1), 20)
                except ValueError:
                    wait = min(2**attempt * 10, 60)
                logger.warning(
                    "llm_rate_limited provider=%s group=%s attempt=%s wait=%.1fs",
                    self.name,
                    group,
                    attempt + 1,
                    wait,
                )
                await asyncio.sleep(wait)
            except json.JSONDecodeError as exc:
                last_error = exc
                await asyncio.sleep(1.0)
        raise RuntimeError(f"LLM request failed for {group} ({type(last_error).__name__})")

    async def healthcheck(self) -> HealthStatus:
        return HealthStatus(
            name=f"llm_{self.name}",
            status="ok",
            detail=f"Configured model={self.model}; connectivity not probed",
            configured=True,
        )


class GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        self.api_key = api_key
        self.model = model or "gemini-2.0-flash"
        self._base = "https://generativelanguage.googleapis.com/v1beta"

    async def extract_group(
        self,
        *,
        group: str,
        fields: list[str],
        evidence_chunks: list[dict[str, Any]],
        source_file: str,
    ) -> dict[str, Any]:
        import httpx

        prompt = {
            "group": group,
            "fields": fields,
            "source_file": source_file,
            "evidence_chunks": evidence_chunks,
            "field_schema": FieldValue.model_json_schema(),
            "instructions": SYSTEM_PROMPT + "\n" + GROUP_INSTRUCTIONS.get(group, ""),
        }
        url = f"{self._base}/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": json.dumps(prompt)}]}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)

    async def healthcheck(self) -> HealthStatus:
        return HealthStatus(
            name="llm_gemini",
            status="ok",
            detail=f"Configured model={self.model}; connectivity not probed",
            configured=bool(self.api_key),
        )


def create_llm_provider(settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "openai":
        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
        return OpenAICompatibleProvider(
            api_key=key,
            base_url=settings.openai_base_url,
            model=settings.llm_model or "gpt-4o-mini",
            provider_name="openai",
            timeout=settings.llm_timeout_seconds,
            max_attempts=settings.llm_max_attempts,
        )
    if settings.llm_provider == "groq":
        key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
        if not key:
            raise ValueError(
                "LLM_PROVIDER=groq requires GROQ_API_KEY; refusing silent fallback to mock"
            )
        return OpenAICompatibleProvider(
            api_key=key,
            base_url=settings.groq_base_url,
            model=settings.llm_model or settings.groq_model or "openai/gpt-oss-20b",
            provider_name="groq",
            timeout=settings.llm_timeout_seconds,
            max_attempts=settings.llm_max_attempts,
            missing_key_message="GROQ_API_KEY is required when LLM_PROVIDER=groq",
        )
    if settings.llm_provider == "gemini":
        key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
        return GeminiProvider(api_key=key, model=settings.gemini_model)
    raise ValueError(f"Unknown LLM_PROVIDER={settings.llm_provider}")
