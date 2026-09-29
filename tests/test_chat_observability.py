from __future__ import annotations

import json
import asyncio
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True


def test_correlation_id_and_headers_propagation(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def run_scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Request 1: Without x-request-id -> should generate req-<8-hex>
            resp1 = await client.post(
                "/chat",
                json={
                    "user_id": "u01",
                    "session_id": "s01",
                    "feature": "qa",
                    "message": "Hello test",
                },
            )
            assert resp1.status_code == 200
            cid1 = resp1.headers.get("x-request-id")
            assert cid1 is not None and cid1.startswith("req-")
            assert "x-response-time-ms" in resp1.headers

            # Request 2: With x-request-id -> should preserve it
            custom_id = "req-custom123"
            resp2 = await client.post(
                "/chat",
                headers={"x-request-id": custom_id},
                json={
                    "user_id": "u02",
                    "session_id": "s02",
                    "feature": "summary",
                    "message": "Summarize this please",
                },
            )
            assert resp2.status_code == 200
            assert resp2.headers.get("x-request-id") == custom_id
            assert resp2.json()["correlation_id"] == custom_id

    asyncio.run(run_scenario())


def test_pii_scrubbed_in_logs_and_context_enrichment(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def run_scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={
                    "user_id": "u05",
                    "session_id": "s05",
                    "feature": "qa",
                    "message": "Call 0987654321 or email test@example.com card 4111 2222 3333 4444",
                },
            )
            assert resp.status_code == 200

    asyncio.run(run_scenario())

    content = log_path.read_text(encoding="utf-8")
    assert "0987654321" not in content
    assert "test@example.com" not in content
    assert "4111 2222 3333 4444" not in content
    assert "REDACTED_PHONE_VN" in content
    assert "REDACTED_EMAIL" in content
    assert "REDACTED_CREDIT_CARD" in content

    # Check enrichment
    lines = [json.loads(line) for line in content.splitlines()]
    api_lines = [l for l in lines if l.get("service") == "api"]
    for l in api_lines:
        assert "user_id_hash" in l
        assert "session_id" in l
        assert "feature" in l
        assert "model" in l
        assert "correlation_id" in l
        assert l["correlation_id"] != "MISSING"
