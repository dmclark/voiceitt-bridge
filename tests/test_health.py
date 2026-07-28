import anyio
import httpx

from voiceitt_bridge import create_app


def test_health_endpoint_reports_server_status() -> None:
    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/health")

    response = anyio.run(request_health)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "voiceitt-bridge"}


def test_root_serves_scratchpad_index() -> None:
    async def request_root() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/")

    response = anyio.run(request_root)

    assert response.status_code == 200
    assert "Voiceitt Scratchpad" in response.text


def test_static_scratchpad_assets_are_served() -> None:
    async def request_script() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/script.js")

    response = anyio.run(request_script)

    assert response.status_code == 200
    assert "initApi" in response.text


def test_api_allows_default_static_scratchpad_origin() -> None:
    async def preflight_prompts() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.options(
                "/api/prompts",
                headers={
                    "origin": "http://localhost:7531",
                    "access-control-request-method": "GET",
                },
            )

    response = anyio.run(preflight_prompts)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:7531"


def test_api_allows_configured_scratchpad_origin(monkeypatch) -> None:
    monkeypatch.setenv("VOICEITT_BRIDGE_PORT", "7631")

    async def preflight_prompts() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.options(
                "/api/prompts",
                headers={
                    "origin": "http://localhost:7631",
                    "access-control-request-method": "GET",
                },
            )

    response = anyio.run(preflight_prompts)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:7631"


def test_api_allows_explicit_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv(
        "VOICEITT_API_CORS_ORIGINS",
        "http://localhost:7631, http://127.0.0.1:7631/",
    )

    async def preflight_prompts() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.options(
                "/api/prompts",
                headers={
                    "origin": "http://127.0.0.1:7631",
                    "access-control-request-method": "GET",
                },
            )

    response = anyio.run(preflight_prompts)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:7631"


def test_scratchpad_state_defaults_to_ai_off_and_empty() -> None:
    async def request_scratchpad_state() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/scratchpad-state")

    response = anyio.run(request_scratchpad_state)

    assert response.status_code == 200
    assert response.json() == {
        "ai_enabled": False,
        "raw_text": "",
        "outgoing_text": "",
        "outgoing_kind": "empty",
    }


def test_scratchpad_state_round_trips_outgoing_text() -> None:
    async def update_and_read_scratchpad_state() -> dict[str, object]:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            update_response = await client.put(
                "/api/scratchpad-state",
                json={
                    "ai_enabled": True,
                    "raw_text": "raw dictated text",
                    "outgoing_text": "cleaned text",
                    "outgoing_kind": "cleaned",
                },
            )
            read_response = await client.get("/api/scratchpad-state")

        assert update_response.status_code == 200
        assert read_response.status_code == 200
        return read_response.json()

    body = anyio.run(update_and_read_scratchpad_state)

    assert body == {
        "ai_enabled": True,
        "raw_text": "raw dictated text",
        "outgoing_text": "cleaned text",
        "outgoing_kind": "cleaned",
    }
