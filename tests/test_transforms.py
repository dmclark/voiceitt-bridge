import asyncio

import anyio
import httpx

from voiceitt_bridge import create_app
from voiceitt_bridge.prompts import PromptDocument
from voiceitt_bridge.storage import InMemoryTransformStore
from voiceitt_bridge.transforms import (
    GeminiTransformProvider,
    ProviderTransformError,
    ProviderUnavailableError,
)


class FakeProvider:
    provider_id = "gemini"
    default_model = "fake-model"

    def __init__(
        self,
        *,
        cleaned_text: str = "cleaned text",
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.cleaned_text = cleaned_text
        self.error = error
        self.delay_seconds = delay_seconds
        self.calls: list[dict[str, object]] = []

    async def transform(
        self,
        *,
        prompt: PromptDocument,
        framed_text: str,
        model: str,
        timeout_ms: int,
    ) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "framed_text": framed_text,
                "model": model,
                "timeout_ms": timeout_ms,
            }
        )
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error:
            raise self.error
        return self.cleaned_text


class FailingTransformStore:
    def record(self, response):
        raise RuntimeError("store locked")

    def recent(self):
        raise RuntimeError("store locked")


def test_gemini_provider_defaults_to_gemini_3_5_flash(monkeypatch) -> None:
    monkeypatch.delenv("VOICEITT_TRANSFORM_MODEL", raising=False)

    provider = GeminiTransformProvider(api_key="test-key")

    assert provider.default_model == "gemini-3.5-flash"


def test_gemini_provider_honors_model_override(monkeypatch) -> None:
    monkeypatch.setenv("VOICEITT_TRANSFORM_MODEL", "configured-model")

    provider = GeminiTransformProvider(api_key="test-key")

    assert provider.default_model == "configured-model"


def test_gemini_provider_reads_key_from_config_env_file(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "env").write_text(
        "# local server-only config\n"
        "export GOOGLE_API_KEY='config-file-key' # keep quoted values working\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("VOICEITT_BRIDGE_CONFIG", str(config_dir))

    provider = GeminiTransformProvider()

    assert provider.api_key == "config-file-key"


def test_gemini_provider_prefers_exported_key_over_config_file(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "env").write_text("GOOGLE_API_KEY=config-file-key\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_API_KEY", "exported-key")
    monkeypatch.setenv("VOICEITT_BRIDGE_CONFIG", str(config_dir))

    provider = GeminiTransformProvider()

    assert provider.api_key == "exported-key"


def test_transform_endpoint_returns_cleaned_text_with_fake_provider(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider(cleaned_text="Make a directory called src.")

    async def request_transform() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(prompts_dir=prompts_dir, transform_provider=provider)
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/transforms",
                json={
                    "raw_text": "make a directory called source",
                    "source": "test",
                    "timeout_ms": 1000,
                },
            )

    response = anyio.run(request_transform)

    assert response.status_code == 200
    body = response.json()
    assert body["raw_text"] == "make a directory called source"
    assert body["cleaned_text"] == "Make a directory called src."
    assert body["status"] == "ok"
    assert body["failure_reason"] is None
    assert body["prompt_id"] == "default"
    assert len(body["prompt_version"]) == 64
    assert body["provider_id"] == "gemini"
    assert body["model"] == "fake-model"
    assert body["source"] == "test"
    assert provider.calls[0]["framed_text"] == (
        "<TRANSCRIPT>\nmake a directory called source\n</TRANSCRIPT>"
    )


def test_transform_endpoint_times_out_and_preserves_raw_text(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider(delay_seconds=0.05)

    async def request_transform() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(prompts_dir=prompts_dir, transform_provider=provider)
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/transforms",
                json={"raw_text": "raw text", "timeout_ms": 1},
            )

    response = anyio.run(request_transform)

    assert response.status_code == 200
    body = response.json()
    assert body["cleaned_text"] == "raw text"
    assert body["status"] == "timeout"
    assert body["failure_reason"] == "provider timed out after 1ms"


def test_transform_endpoint_provider_error_preserves_raw_text(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider(error=ProviderTransformError("provider broke"))

    async def request_transform() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(prompts_dir=prompts_dir, transform_provider=provider)
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post("/api/transforms", json={"raw_text": "raw text"})

    response = anyio.run(request_transform)

    assert response.status_code == 200
    body = response.json()
    assert body["cleaned_text"] == "raw text"
    assert body["status"] == "provider_error"
    assert body["failure_reason"] == "provider broke"


def test_transform_endpoint_disabled_request_preserves_raw_text(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider()

    async def request_transform() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(prompts_dir=prompts_dir, transform_provider=provider)
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/transforms",
                json={"raw_text": "raw text", "enabled": False},
            )

    response = anyio.run(request_transform)

    assert response.status_code == 200
    body = response.json()
    assert body["cleaned_text"] == "raw text"
    assert body["status"] == "disabled"
    assert body["failure_reason"] == "transform disabled by request"
    assert provider.calls == []


def test_transform_endpoint_provider_unavailable_is_disabled(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider(error=ProviderUnavailableError("GOOGLE_API_KEY is not set"))

    async def request_transform() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(prompts_dir=prompts_dir, transform_provider=provider)
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post("/api/transforms", json={"raw_text": "raw text"})

    response = anyio.run(request_transform)

    assert response.status_code == 200
    body = response.json()
    assert body["cleaned_text"] == "raw text"
    assert body["status"] == "disabled"
    assert body["failure_reason"] == "GOOGLE_API_KEY is not set"


def test_transform_endpoint_empty_input_does_not_call_provider(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider()

    async def request_transform() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(prompts_dir=prompts_dir, transform_provider=provider)
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post("/api/transforms", json={"raw_text": ""})

    response = anyio.run(request_transform)

    assert response.status_code == 200
    body = response.json()
    assert body["raw_text"] == ""
    assert body["cleaned_text"] == ""
    assert body["status"] == "empty_input"
    assert body["failure_reason"] is None
    assert provider.calls == []


def test_transform_endpoint_records_metadata_only_recent_transform(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider(cleaned_text="cleaned")
    store = InMemoryTransformStore(max_records=2)

    async def record_and_read_recent() -> list[dict[str, object]]:
        transport = httpx.ASGITransport(
            app=create_app(
                prompts_dir=prompts_dir,
                transform_provider=provider,
                transform_store=store,
            )
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first_response = await client.post(
                "/api/transforms",
                json={"raw_text": "raw one", "source": "scratchpad"},
            )
            second_response = await client.post(
                "/api/transforms",
                json={"raw_text": "raw two", "source": "raycast"},
            )
            recent_response = await client.get("/api/transforms/recent")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert recent_response.status_code == 200
        return recent_response.json()

    recent = anyio.run(record_and_read_recent)

    assert [record["source"] for record in recent] == ["raycast", "scratchpad"]
    assert recent[0]["status"] == "ok"
    assert recent[0]["raw_text_length"] == len("raw two")
    assert recent[0]["cleaned_text_length"] == len("cleaned")
    assert "raw_text" not in recent[0]
    assert "cleaned_text" not in recent[0]


def test_recent_transforms_are_bounded(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider(cleaned_text="cleaned")
    store = InMemoryTransformStore(max_records=1)

    async def record_and_read_recent() -> list[dict[str, object]]:
        transport = httpx.ASGITransport(
            app=create_app(
                prompts_dir=prompts_dir,
                transform_provider=provider,
                transform_store=store,
            )
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            await client.post("/api/transforms", json={"raw_text": "first"})
            await client.post("/api/transforms", json={"raw_text": "second"})
            recent_response = await client.get("/api/transforms/recent")

        assert recent_response.status_code == 200
        return recent_response.json()

    recent = anyio.run(record_and_read_recent)

    assert len(recent) == 1
    assert recent[0]["raw_text_length"] == len("second")


def test_transform_storage_failure_does_not_block_transform_success(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")
    provider = FakeProvider(cleaned_text="cleaned")

    async def request_transform() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(
                prompts_dir=prompts_dir,
                transform_provider=provider,
                transform_store=FailingTransformStore(),
            )
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post("/api/transforms", json={"raw_text": "raw text"})

    response = anyio.run(request_transform)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["cleaned_text"] == "cleaned"


def test_recent_transforms_returns_empty_list_when_store_fails(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")

    async def request_recent() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(
                prompts_dir=prompts_dir,
                transform_provider=FakeProvider(),
                transform_store=FailingTransformStore(),
            )
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/transforms/recent")

    response = anyio.run(request_recent)

    assert response.status_code == 200
    assert response.json() == []
