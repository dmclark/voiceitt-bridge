import anyio
import httpx
import pytest

from voiceitt_bridge import create_app
from voiceitt_bridge.prompts import (
    PromptNotFoundError,
    frame_transcript,
    load_prompt_by_id,
)


def test_prompts_endpoint_lists_default_prompt_metadata() -> None:
    async def request_prompts() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/prompts")

    response = anyio.run(request_prompts)

    assert response.status_code == 200
    prompts = response.json()
    assert prompts == [
        {
            "id": "default",
            "name": "default",
            "path": "prompts/default.md",
            "content_hash": prompts[0]["content_hash"],
        }
    ]
    assert len(prompts[0]["content_hash"]) == 64
    assert "system_text" not in prompts[0]


def test_prompts_preview_renders_prompt_file_contents(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text(
        "Clean <TRANSCRIPT> text & preserve intent.",
        encoding="utf-8",
    )

    async def request_prompts_preview() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/prompts/preview")

    response = anyio.run(request_prompts_preview)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Voiceitt Bridge Prompts" in response.text
    assert "default" in response.text
    assert "prompts/default.md" in response.text
    assert "Clean &lt;TRANSCRIPT&gt; text &amp; preserve intent." in response.text


def test_prompts_endpoint_returns_empty_list_for_missing_prompt_dir(tmp_path) -> None:
    async def request_prompts() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=create_app(prompts_dir=tmp_path / "missing-prompts")
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/prompts")

    response = anyio.run(request_prompts)

    assert response.status_code == 200
    assert response.json() == []


def test_prompts_endpoint_uses_stable_filename_ids(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")
    (prompts_dir / "plain-language.md").write_text("plain", encoding="utf-8")

    async def request_prompts() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/prompts")

    response = anyio.run(request_prompts)

    assert response.status_code == 200
    assert [prompt["id"] for prompt in response.json()] == [
        "default",
        "plain-language",
    ]


def test_prompt_read_endpoint_returns_full_prompt_text(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("Clean transcripts.", encoding="utf-8")

    async def request_prompt() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/prompts/default")

    response = anyio.run(request_prompt)

    assert response.status_code == 200
    prompt = response.json()
    assert prompt["id"] == "default"
    assert prompt["system_text"] == "Clean transcripts."


def test_prompt_validate_endpoint_reports_authoring_errors(tmp_path) -> None:
    async def validate_prompt() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=tmp_path / "prompts"))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/prompts/validate",
                json={"id": "Bad/Path", "system_text": "   "},
            )

    response = anyio.run(validate_prompt)

    assert response.status_code == 200
    assert response.json() == {
        "ok": False,
        "errors": [
            "prompt id must be lowercase letters, numbers, or hyphens",
            "system_text must not be empty",
        ],
    }


def test_prompt_create_update_and_active_selection(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"

    async def write_prompt() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            create_response = await client.post(
                "/api/prompts",
                json={"id": "plain-language", "system_text": "Clean plainly."},
            )
            update_response = await client.put(
                "/api/prompts/plain-language",
                json={"system_text": "Clean very plainly."},
            )
            state_response = await client.put(
                "/api/prompt-state",
                json={
                    "active_prompt_id": "plain-language",
                    "updated_by": "test",
                },
            )

        assert create_response.status_code == 200
        assert update_response.status_code == 200
        assert state_response.status_code == 200
        return create_response.json(), update_response.json(), state_response.json()

    created, updated, state = anyio.run(write_prompt)

    assert created["id"] == "plain-language"
    assert created["system_text"] == "Clean plainly."
    assert updated["system_text"] == "Clean very plainly."
    assert (prompts_dir / "user" / "plain-language.md").read_text(
        encoding="utf-8"
    ) == (
        "Clean very plainly."
    )
    assert state["active_prompt_id"] == "plain-language"
    assert state["updated_by"] == "test"


def test_prompt_update_writes_user_override_for_system_prompt(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("system default", encoding="utf-8")

    async def override_prompt() -> tuple[dict[str, str], list[dict[str, str]]]:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            update_response = await client.put(
                "/api/prompts/default",
                json={"system_text": "user default"},
            )
            prompts_response = await client.get("/api/prompts")

        assert update_response.status_code == 200
        assert prompts_response.status_code == 200
        return update_response.json(), prompts_response.json()

    updated, prompts = anyio.run(override_prompt)

    assert updated["system_text"] == "user default"
    assert updated["path"] == "prompts/user/default.md"
    assert prompts[0]["path"] == "prompts/user/default.md"
    assert (prompts_dir / "default.md").read_text(encoding="utf-8") == "system default"
    assert (prompts_dir / "user" / "default.md").read_text(encoding="utf-8") == (
        "user default"
    )


def test_prompt_create_rejects_system_prompt_id(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("system default", encoding="utf-8")

    async def create_prompt() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/prompts",
                json={"id": "default", "system_text": "new default"},
            )

    response = anyio.run(create_prompt)

    assert response.status_code == 409
    assert response.json() == {"detail": "prompt already exists: default"}


def test_prompt_create_rejects_invalid_prompt_input(tmp_path) -> None:
    async def create_prompt() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=tmp_path / "prompts"))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/prompts",
                json={"id": "../bad", "system_text": ""},
            )

    response = anyio.run(create_prompt)

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            "prompt id must be lowercase letters, numbers, or hyphens",
            "system_text must not be empty",
        ]
    }


def test_prompt_archive_removes_prompt_and_resets_active_prompt(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")
    user_prompts_dir = prompts_dir / "user"
    user_prompts_dir.mkdir()
    (user_prompts_dir / "plain-language.md").write_text("plain", encoding="utf-8")

    async def archive_prompt() -> tuple[dict[str, str], list[dict[str, str]], httpx.Response]:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            state_response = await client.put(
                "/api/prompt-state",
                json={
                    "active_prompt_id": "plain-language",
                    "updated_by": "test",
                },
            )
            archive_response = await client.post("/api/prompts/plain-language/archive")
            prompts_response = await client.get("/api/prompts")
            read_response = await client.get("/api/prompts/plain-language")

        assert state_response.status_code == 200
        assert archive_response.status_code == 200
        assert prompts_response.status_code == 200
        return archive_response.json(), prompts_response.json(), read_response

    state, prompts, read_response = anyio.run(archive_prompt)

    assert state["active_prompt_id"] == "default"
    assert state["updated_by"] == "prompt-archive"
    assert [prompt["id"] for prompt in prompts] == ["default"]
    assert read_response.status_code == 404
    assert not (user_prompts_dir / "plain-language.md").exists()
    assert list((user_prompts_dir / ".archived").glob("plain-language.*.md"))


def test_prompt_archive_removes_user_override_without_archiving_system_prompt(
    tmp_path,
) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("system default", encoding="utf-8")
    user_prompts_dir = prompts_dir / "user"
    user_prompts_dir.mkdir()
    (user_prompts_dir / "default.md").write_text("user default", encoding="utf-8")

    async def archive_prompt() -> tuple[dict[str, str], dict[str, str]]:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            archive_response = await client.post("/api/prompts/default/archive")
            read_response = await client.get("/api/prompts/default")

        assert archive_response.status_code == 200
        assert read_response.status_code == 200
        return archive_response.json(), read_response.json()

    state, prompt = anyio.run(archive_prompt)

    assert state["active_prompt_id"] == "default"
    assert prompt["path"] == "prompts/default.md"
    assert prompt["system_text"] == "system default"
    assert not (user_prompts_dir / "default.md").exists()
    assert list((user_prompts_dir / ".archived").glob("default.*.md"))


def test_prompt_archive_rejects_system_managed_prompt_without_user_override(
    tmp_path,
) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("system default", encoding="utf-8")

    async def archive_prompt() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post("/api/prompts/default/archive")

    response = anyio.run(archive_prompt)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "system-managed prompt cannot be archived: default"
    }


def test_prompt_state_endpoint_defaults_to_first_prompt(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")
    (prompts_dir / "plain-language.md").write_text("plain", encoding="utf-8")

    async def request_prompt_state() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/prompt-state")

    response = anyio.run(request_prompt_state)

    assert response.status_code == 200
    state = response.json()
    assert state["active_prompt_id"] == "default"
    assert state["updated_by"] == "server-default"
    assert state["updated_at"].endswith("Z")


def test_prompt_state_endpoint_rejects_unknown_prompt_id(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")

    async def update_prompt_state() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.put(
                "/api/prompt-state",
                json={
                    "active_prompt_id": "missing",
                    "updated_by": "scratchpad",
                },
            )

    response = anyio.run(update_prompt_state)

    assert response.status_code == 404
    assert response.json() == {"detail": "unknown prompt id"}


def test_prompt_state_endpoint_uses_last_write_wins(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")
    (prompts_dir / "plain-language.md").write_text("plain", encoding="utf-8")

    async def update_prompt_state() -> tuple[dict[str, str], dict[str, str]]:
        transport = httpx.ASGITransport(app=create_app(prompts_dir=prompts_dir))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            first_response = await client.put(
                "/api/prompt-state",
                json={
                    "active_prompt_id": "plain-language",
                    "updated_by": "scratchpad",
                },
            )
            second_response = await client.put(
                "/api/prompt-state",
                json={
                    "active_prompt_id": "default",
                    "updated_by": "raycast-script",
                },
            )
            current_response = await client.get("/api/prompt-state")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert current_response.status_code == 200
        return second_response.json(), current_response.json()

    second_state, current_state = anyio.run(update_prompt_state)

    assert second_state["active_prompt_id"] == "default"
    assert second_state["updated_by"] == "raycast-script"
    assert current_state == second_state


def test_frame_transcript_wraps_user_text() -> None:
    assert frame_transcript("make a directory called src") == (
        "<TRANSCRIPT>\nmake a directory called src\n</TRANSCRIPT>"
    )


def test_frame_transcript_empty_text_behavior_is_explicit() -> None:
    assert frame_transcript("") == "<TRANSCRIPT>\n\n</TRANSCRIPT>"


def test_load_prompt_by_id_returns_utf8_system_text(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text(
        "Clean café transcripts.\n",
        encoding="utf-8",
    )

    prompt = load_prompt_by_id(prompts_dir, "default")

    assert prompt["id"] == "default"
    assert prompt["name"] == "default"
    assert prompt["path"] == "prompts/default.md"
    assert len(prompt["content_hash"]) == 64
    assert prompt["system_text"] == "Clean café transcripts.\n"


def test_load_prompt_by_id_accepts_matching_content_hash(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")
    prompt = load_prompt_by_id(prompts_dir, "default")

    reloaded = load_prompt_by_id(
        prompts_dir,
        "default",
        content_hash=prompt["content_hash"],
    )

    assert reloaded == prompt


def test_load_prompt_by_id_rejects_missing_prompt(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")

    with pytest.raises(PromptNotFoundError, match="unknown prompt id: missing"):
        load_prompt_by_id(prompts_dir, "missing")


def test_load_prompt_by_id_rejects_hash_mismatch(tmp_path) -> None:
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "default.md").write_text("default", encoding="utf-8")

    with pytest.raises(PromptNotFoundError, match="prompt hash mismatch: default"):
        load_prompt_by_id(prompts_dir, "default", content_hash="not-the-hash")
