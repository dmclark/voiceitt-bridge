"""FastAPI application factory for Voiceitt Bridge."""

from html import escape
import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from voiceitt_bridge.prompts import (
    ActivePromptState,
    PromptAlreadyExistsError,
    PromptDocument,
    PromptNotFoundError,
    PromptStore,
    PromptStateUpdate,
    PromptSystemManagedError,
    PromptSummary,
    PromptValidationError,
    PromptValidationRequest,
    PromptValidationResult,
    PromptWrite,
)
from voiceitt_bridge.storage import (
    InMemoryTransformStore,
    TransformRecord,
    TransformStore,
)
from voiceitt_bridge.transforms import (
    GeminiTransformProvider,
    TransformProvider,
    TransformRequest,
    TransformResponse,
    run_transform,
)


OutgoingTextKind = Literal["raw", "cleaned", "edited", "empty"]


class ScratchpadRuntimeState(BaseModel):
    """Browser-owned scratchpad state that Raycast can read via the API."""

    ai_enabled: bool = False
    raw_text: str = ""
    outgoing_text: str = ""
    outgoing_kind: OutgoingTextKind = "empty"


class ScratchpadRuntimeStateUpdate(BaseModel):
    """Full-state update pushed by the scratchpad browser page."""

    ai_enabled: bool
    raw_text: str = ""
    outgoing_text: str = ""
    outgoing_kind: OutgoingTextKind = "empty"


def create_app(
    prompts_dir: Path | str = "prompts",
    *,
    web_dir: Path | str = "web",
    transform_provider: TransformProvider | None = None,
    transform_store: TransformStore | None = None,
) -> FastAPI:
    """Create the FastAPI app that serves the scratchpad and API."""
    app = FastAPI(title="Voiceitt Bridge API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["content-type"],
    )
    prompt_store = PromptStore(prompts_dir)
    scratchpad_web_dir = Path(web_dir)
    provider = transform_provider or GeminiTransformProvider()
    scratchpad_runtime_state = ScratchpadRuntimeState()
    store = transform_store or InMemoryTransformStore()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "voiceitt-bridge"}

    @app.get("/api/prompts")
    def prompts() -> list[PromptSummary]:
        return prompt_store.list_prompts()

    @app.post("/api/prompts")
    def create_prompt(prompt: PromptWrite) -> PromptDocument:
        if prompt.id is None:
            raise HTTPException(status_code=422, detail="prompt id is required")
        try:
            return prompt_store.create_prompt(
                prompt_id=prompt.id,
                system_text=prompt.system_text,
            )
        except PromptValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors) from error
        except PromptAlreadyExistsError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/prompts/validate")
    def validate_prompt(prompt: PromptValidationRequest) -> PromptValidationResult:
        return prompt_store.validate_prompt(
            prompt_id=prompt.id,
            system_text=prompt.system_text,
        )

    @app.get("/api/prompts/preview", response_class=HTMLResponse)
    def prompts_preview() -> str:
        prompt_documents = [
            prompt_store.load_prompt(prompt["id"])
            for prompt in prompt_store.list_prompts()
        ]
        return _render_prompts_preview(prompt_documents)

    @app.get("/api/prompts/{prompt_id}")
    def read_prompt(prompt_id: str) -> PromptDocument:
        try:
            return prompt_store.load_prompt(prompt_id)
        except PromptNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.put("/api/prompts/{prompt_id}")
    def update_prompt(prompt_id: str, prompt: PromptWrite) -> PromptDocument:
        try:
            return prompt_store.update_prompt(
                prompt_id=prompt_id,
                system_text=prompt.system_text,
            )
        except PromptValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors) from error
        except PromptNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/prompts/{prompt_id}/archive")
    def archive_prompt(prompt_id: str) -> ActivePromptState:
        try:
            return prompt_store.archive_prompt(prompt_id)
        except PromptSystemManagedError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except PromptNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/prompt-state")
    def prompt_state() -> ActivePromptState:
        return prompt_store.get_active_prompt_state()

    @app.put("/api/prompt-state")
    def update_prompt_state(update: PromptStateUpdate) -> ActivePromptState:
        try:
            return prompt_store.set_active_prompt_state(update)
        except PromptNotFoundError as error:
            raise HTTPException(status_code=404, detail="unknown prompt id") from error

    @app.get("/api/scratchpad-state")
    def scratchpad_state() -> ScratchpadRuntimeState:
        return scratchpad_runtime_state

    @app.put("/api/scratchpad-state")
    def update_scratchpad_state(
        update: ScratchpadRuntimeStateUpdate,
    ) -> ScratchpadRuntimeState:
        nonlocal scratchpad_runtime_state
        scratchpad_runtime_state = ScratchpadRuntimeState(**update.model_dump())
        return scratchpad_runtime_state

    @app.post("/api/transforms")
    async def transform(request: TransformRequest) -> TransformResponse:
        prompt_id = request.prompt_id or prompt_store.get_active_prompt_state()[
            "active_prompt_id"
        ]
        request = request.model_copy(update={"prompt_id": prompt_id})
        prompt = None
        if request.raw_text and request.enabled and request.provider_id == provider.provider_id:
            try:
                prompt = prompt_store.load_prompt(prompt_id)
            except PromptNotFoundError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error

        response = await run_transform(
            request=request,
            prompt=prompt,
            provider=provider,
        )
        try:
            store.record(response)
        except Exception:
            pass
        return response

    @app.get("/api/transforms/recent")
    def recent_transforms() -> list[TransformRecord]:
        try:
            return store.recent()
        except Exception:
            return []

    app.mount(
        "/",
        StaticFiles(directory=scratchpad_web_dir, html=True),
        name="scratchpad",
    )

    return app


def _cors_origins() -> list[str]:
    """Return local scratchpad origins allowed to call the API."""

    configured_origins = os.environ.get("VOICEITT_API_CORS_ORIGINS")
    if configured_origins:
        origins = [origin.strip() for origin in configured_origins.split(",")]
        return [origin.rstrip("/") for origin in origins if origin.strip()]

    scratchpad_port = os.environ.get("VOICEITT_BRIDGE_PORT", "7531")
    return [
        f"http://localhost:{scratchpad_port}",
        f"http://127.0.0.1:{scratchpad_port}",
    ]


def _render_prompts_preview(prompts: list[dict[str, str]]) -> str:
    """Render a local browser preview of prompt files.

    `/api/prompts` stays metadata-only JSON for API clients. This page is
    intentionally separate so a human can inspect what each prompt picker
    selection does without changing the API contract.
    """
    prompt_sections = []
    for prompt in prompts:
        prompt_id = escape(prompt["id"])
        prompt_sections.append(
            f"""
            <section class="prompt" id="{prompt_id}">
              <h2>{prompt_id}</h2>
              <dl>
                <dt>path</dt><dd>{escape(prompt["path"])}</dd>
                <dt>hash</dt><dd><code>{escape(prompt["content_hash"])}</code></dd>
              </dl>
              <pre>{escape(prompt["system_text"])}</pre>
            </section>
            """
        )

    body = "\n".join(prompt_sections) or "<p>No prompts found.</p>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Voiceitt Bridge Prompts</title>
  <style>
    body {{
      margin: 0;
      padding: 24px;
      background: #fafaf7;
      color: #1a1a1a;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
      line-height: 1.5;
    }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }}
    .subtitle {{ margin: 0; color: #666; }}
    .prompt {{
      margin: 0 0 24px;
      padding: 16px;
      border: 1px solid #e0dfd9;
      border-radius: 8px;
      background: #fffef9;
    }}
    h2 {{ margin: 0 0 8px; font-size: 18px; }}
    dl {{ display: grid; grid-template-columns: max-content 1fr; gap: 4px 10px; margin: 0 0 12px; color: #666; font-size: 13px; }}
    dt {{ font-weight: 700; }}
    dd {{ margin: 0; }}
    pre {{
      white-space: pre-wrap;
      margin: 0;
      padding: 12px;
      background: #f5f4ef;
      border-radius: 6px;
      overflow-wrap: anywhere;
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Voiceitt Bridge Prompts</h1>
    <p class="subtitle">Local preview of cleanup prompt files available to the scratchpad picker.</p>
  </header>
  {body}
</body>
</html>"""


app = create_app()
