"""Tests for ZephyrClient (ZAPI) with mocked HTTP transport."""

import pytest
import httpx
from zephyr_jira_mcp.zephyr_client import ZephyrClient
from zephyr_jira_mcp.models import TestStepSpec


@pytest.mark.asyncio
async def test_get_test_steps(mock_settings):
    def handler(request: httpx.Request):
        assert request.url.path == "/rest/zapi/latest/teststep/10999"
        return httpx.Response(200, json=[
            {"id": 1, "step": "Step 1", "data": "Data 1", "result": "Result 1"}
        ])

    client = ZephyrClient(mock_settings)
    client._get_client = lambda: httpx.AsyncClient(
        base_url=mock_settings.jira_base_url,
        transport=httpx.MockTransport(handler),
    )

    steps = await client.get_test_steps("10999")
    assert len(steps) == 1
    assert steps[0]["step"] == "Step 1"


@pytest.mark.asyncio
async def test_add_test_step_with_transient_retry(mock_settings):
    attempts = 0

    def handler(request: httpx.Request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # Simulate transient gateway error
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(200, json={"id": 42, "status": "created"})

    client = ZephyrClient(mock_settings)
    client._get_client = lambda: httpx.AsyncClient(
        base_url=mock_settings.jira_base_url,
        transport=httpx.MockTransport(handler),
    )

    res = await client.add_test_step(
        issue_id="10999",
        step="Verify status",
        data="200 OK",
        result="Success",
    )
    assert attempts == 2
    assert res["id"] == 42


@pytest.mark.asyncio
async def test_add_test_steps_batch(mock_settings):
    created_count = 0

    def handler(request: httpx.Request):
        nonlocal created_count
        created_count += 1
        return httpx.Response(200, json={"id": created_count})

    client = ZephyrClient(mock_settings)
    client._get_client = lambda: httpx.AsyncClient(
        base_url=mock_settings.jira_base_url,
        transport=httpx.MockTransport(handler),
    )

    steps = [
        TestStepSpec(step="Step 1", data="D1", result="R1"),
        TestStepSpec(step="Step 2", data="D2", result="R2"),
    ]
    res = await client.add_test_steps_batch("10999", steps)
    assert len(res) == 2
    assert created_count == 2
