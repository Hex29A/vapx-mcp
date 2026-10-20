"""
Tests for bearer-token auth on the HTTP transports.

The middleware is exercised against a stub inner app, and the real SSE and
streamable-HTTP apps are checked through an in-process ASGI client, so no
port is opened.
"""

import secrets

import httpx
import pytest

import server as srv

TOKEN = secrets.token_hex(16)


async def _stub_app(scope, receive, send):
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
    })
    await send({"type": "http.response.body", "body": b"reached handler"})


def _client(asgi_app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=asgi_app), base_url="http://test"
    )


@pytest.fixture
def guarded():
    return srv.BearerAuthMiddleware(_stub_app, TOKEN)


class TestBearerAuthMiddleware:
    async def test_no_token_gets_401(self, guarded):
        async with _client(guarded) as c:
            r = await c.get("/")
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"

    async def test_wrong_token_gets_401(self, guarded):
        async with _client(guarded) as c:
            r = await c.get("/", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    async def test_wrong_scheme_gets_401(self, guarded):
        async with _client(guarded) as c:
            r = await c.get("/", headers={"Authorization": f"Basic {TOKEN}"})
        assert r.status_code == 401

    async def test_token_without_scheme_gets_401(self, guarded):
        async with _client(guarded) as c:
            r = await c.get("/", headers={"Authorization": TOKEN})
        assert r.status_code == 401

    async def test_right_token_reaches_handler(self, guarded):
        async with _client(guarded) as c:
            r = await c.get("/", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 200
        assert r.text == "reached handler"

    async def test_scheme_is_case_insensitive(self, guarded):
        async with _client(guarded) as c:
            r = await c.get("/", headers={"Authorization": f"bearer {TOKEN}"})
        assert r.status_code == 200


class TestRealApps:
    async def test_streamable_http_rejects_without_token(self):
        app = srv.build_streamable_http_app(TOKEN)
        async with _client(app) as c:
            r = await c.post("/mcp/", json={})
        assert r.status_code == 401

    async def test_streamable_http_wrong_token(self):
        app = srv.build_streamable_http_app(TOKEN)
        async with _client(app) as c:
            r = await c.post(
                "/mcp/", json={}, headers={"Authorization": "Bearer nope"}
            )
        assert r.status_code == 401

    async def test_streamable_http_right_token_reaches_mcp(self):
        app = srv.build_streamable_http_app(TOKEN)
        # The session manager is started by the inner app's lifespan.
        async with app.app.router.lifespan_context(app.app):
            async with _client(app) as c:
                r = await c.post(
                    "/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "0"},
                        },
                    },
                    headers={
                        "Authorization": f"Bearer {TOKEN}",
                        "Accept": "application/json, text/event-stream",
                    },
                )
        assert r.status_code == 200
        assert r.json()["result"]["serverInfo"]["name"]

    async def test_sse_rejects_without_token(self):
        app = srv.build_sse_app(TOKEN)
        async with _client(app) as c:
            r = await c.get("/sse")
        assert r.status_code == 401

    async def test_sse_message_post_rejected_without_token(self):
        app = srv.build_sse_app(TOKEN)
        async with _client(app) as c:
            r = await c.post("/messages/?session_id=abc", json={})
        assert r.status_code == 401

    def test_no_token_means_no_middleware(self):
        # Only reachable through --insecure-no-auth.
        assert not isinstance(
            srv.build_streamable_http_app(None), srv.BearerAuthMiddleware
        )


class TestStartupRefusal:
    @pytest.mark.parametrize("transport", ["sse", "streamable-http"])
    async def test_http_without_token_exits_nonzero(
        self, monkeypatch, transport
    ):
        monkeypatch.delenv(srv.TOKEN_ENV_VAR, raising=False)
        monkeypatch.setattr("sys.argv", ["server.py", "--transport", transport])
        with pytest.raises(SystemExit) as exc:
            await srv.main()
        assert exc.value.code != 0

    async def test_blank_token_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv(srv.TOKEN_ENV_VAR, "   ")
        monkeypatch.setattr(
            "sys.argv", ["server.py", "--transport", "streamable-http"]
        )
        with pytest.raises(SystemExit) as exc:
            await srv.main()
        assert exc.value.code != 0
