"""Transform service boundary for the Voiceitt Bridge API."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import socket
import time
import urllib.error
import urllib.request
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from voiceitt_bridge.prompts import PromptDocument, frame_transcript


TransformStatus = Literal[
    "ok",
    "fail_open",
    "timeout",
    "provider_error",
    "disabled",
    "empty_input",
]


class TransformRequest(BaseModel):
    """Request body for cleanup transforms."""

    raw_text: str
    prompt_id: str | None = None
    vocabulary_profile_ids: list[str] = Field(default_factory=list)
    provider_id: str = "gemini"
    model: str | None = None
    source: str = "scratchpad"
    timeout_ms: int = Field(default=6000, gt=0)
    enabled: bool = True


class TransformResponse(BaseModel):
    """Structured transform result with fail-open metadata."""

    raw_text: str
    cleaned_text: str
    status: TransformStatus
    failure_reason: str | None = None
    prompt_id: str
    prompt_version: str
    vocabulary_profile_ids: list[str]
    provider_id: str
    model: str
    source: str
    duration_ms: int


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider is intentionally unavailable/disabled."""


class ProviderTransformError(RuntimeError):
    """Raised when a provider returns an unusable transform result."""


class TransformProvider(Protocol):
    """Async provider interface used by the transform service."""

    provider_id: str
    default_model: str

    async def transform(
        self,
        *,
        prompt: PromptDocument,
        framed_text: str,
        model: str,
        timeout_ms: int,
    ) -> str:
        """Return provider-cleaned text or raise a provider exception."""


class GeminiTransformProvider:
    """Gemini REST provider that keeps API keys on the server."""

    provider_id = "gemini"
    api_base = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else _configured_google_api_key()
        self.default_model = default_model or os.environ.get(
            "VOICEITT_TRANSFORM_MODEL",
            "gemini-3.1-flash-lite",
        )

    async def transform(
        self,
        *,
        prompt: PromptDocument,
        framed_text: str,
        model: str,
        timeout_ms: int,
    ) -> str:
        if not self.api_key:
            raise ProviderUnavailableError("GOOGLE_API_KEY is not set")

        return await asyncio.to_thread(
            self._transform_sync,
            prompt=prompt,
            framed_text=framed_text,
            model=model,
            timeout_ms=timeout_ms,
        )

    def _transform_sync(
        self,
        *,
        prompt: PromptDocument,
        framed_text: str,
        model: str,
        timeout_ms: int,
    ) -> str:
        request_body = {
            "system_instruction": {"parts": [{"text": prompt["system_text"]}]},
            "contents": [{"role": "user", "parts": [{"text": framed_text}]}],
            "generationConfig": {"temperature": 0.2},
        }
        url = f"{self.api_base}/{model}:generateContent?key={self.api_key}"
        request = urllib.request.Request(
            url,
            data=json.dumps(request_body).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_ms / 1000) as response:
                response_text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            raise ProviderTransformError(f"Gemini returned HTTP {error.code}") from error
        except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
            raise ProviderTransformError(f"Gemini request failed: {error}") from error

        try:
            parsed = json.loads(response_text)
            cleaned = parsed["candidates"][0]["content"]["parts"][0]["text"] or ""
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise ProviderTransformError("Gemini returned an unusable response") from error

        if not cleaned:
            raise ProviderTransformError("Gemini returned empty cleaned text")

        return cleaned


async def run_transform(
    *,
    request: TransformRequest,
    prompt: PromptDocument | None,
    provider: TransformProvider,
) -> TransformResponse:
    """Run one transform attempt and always preserve raw text for fail-open."""
    started = time.monotonic()
    prompt_id = prompt["id"] if prompt else request.prompt_id or ""
    prompt_version = prompt["content_hash"] if prompt else ""
    model = request.model or provider.default_model

    if not request.raw_text:
        return _response(
            request=request,
            raw_text=request.raw_text,
            cleaned_text="",
            status="empty_input",
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider.provider_id,
            model=model,
            started=started,
        )

    if not request.enabled:
        return _response(
            request=request,
            raw_text=request.raw_text,
            cleaned_text=request.raw_text,
            status="disabled",
            failure_reason="transform disabled by request",
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider.provider_id,
            model=model,
            started=started,
        )

    if request.provider_id != provider.provider_id:
        return _response(
            request=request,
            raw_text=request.raw_text,
            cleaned_text=request.raw_text,
            status="provider_error",
            failure_reason=f"unknown provider id: {request.provider_id}",
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider.provider_id,
            model=model,
            started=started,
        )

    if prompt is None:
        return _response(
            request=request,
            raw_text=request.raw_text,
            cleaned_text=request.raw_text,
            status="provider_error",
            failure_reason="prompt is required for non-empty transforms",
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider.provider_id,
            model=model,
            started=started,
        )

    try:
        cleaned_text = await asyncio.wait_for(
            provider.transform(
                prompt=prompt,
                framed_text=frame_transcript(request.raw_text),
                model=model,
                timeout_ms=request.timeout_ms,
            ),
            timeout=request.timeout_ms / 1000,
        )
    except TimeoutError:
        return _response(
            request=request,
            raw_text=request.raw_text,
            cleaned_text=request.raw_text,
            status="timeout",
            failure_reason=f"provider timed out after {request.timeout_ms}ms",
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider.provider_id,
            model=model,
            started=started,
        )
    except ProviderUnavailableError as error:
        return _response(
            request=request,
            raw_text=request.raw_text,
            cleaned_text=request.raw_text,
            status="disabled",
            failure_reason=str(error),
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider.provider_id,
            model=model,
            started=started,
        )
    except ProviderTransformError as error:
        return _response(
            request=request,
            raw_text=request.raw_text,
            cleaned_text=request.raw_text,
            status="provider_error",
            failure_reason=str(error),
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            provider_id=provider.provider_id,
            model=model,
            started=started,
        )

    return _response(
        request=request,
        raw_text=request.raw_text,
        cleaned_text=cleaned_text,
        status="ok",
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        provider_id=provider.provider_id,
        model=model,
        started=started,
    )


def _configured_google_api_key() -> str | None:
    """Return the Gemini key from the process env or local config env file.

    The Raycast launcher sources `~/.config/voiceitt-bridge/env` before
    starting the runtime, but the FastAPI app can also be started directly
    with `uv run uvicorn ...`. Falling back to the same server-side env file
    keeps API keys out of the browser and makes both launch paths consistent.
    """
    env_key = os.environ.get("GOOGLE_API_KEY")
    if env_key:
        return env_key

    config_dir = os.environ.get(
        "VOICEITT_BRIDGE_CONFIG",
        os.path.join(os.path.expanduser("~"), ".config", "voiceitt-bridge"),
    )
    env_path = os.path.join(config_dir, "env")
    try:
        with open(env_path, encoding="utf-8") as env_file:
            for raw_line in env_file:
                key = _parse_google_api_key_line(raw_line)
                if key:
                    return key
    except OSError:
        return None

    return None


def _parse_google_api_key_line(line: str) -> str | None:
    """Parse one shell-env line without executing it."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :].lstrip()
    if not stripped.startswith("GOOGLE_API_KEY="):
        return None

    value = stripped.split("=", 1)[1]
    try:
        parts = shlex.split(value, comments=True, posix=True)
    except ValueError:
        return value.strip().strip("'\"") or None
    return parts[0] if parts else ""


def _response(
    *,
    request: TransformRequest,
    raw_text: str,
    cleaned_text: str,
    status: TransformStatus,
    prompt_id: str,
    prompt_version: str,
    provider_id: str,
    model: str,
    started: float,
    failure_reason: str | None = None,
) -> TransformResponse:
    return TransformResponse(
        raw_text=raw_text,
        cleaned_text=cleaned_text,
        status=status,
        failure_reason=failure_reason,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        vocabulary_profile_ids=request.vocabulary_profile_ids,
        provider_id=provider_id,
        model=model,
        source=request.source,
        duration_ms=max(0, round((time.monotonic() - started) * 1000)),
    )
