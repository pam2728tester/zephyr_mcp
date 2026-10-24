"""Tests for JiraClient with mocked HTTP transport."""

import pytest
import httpx
from zephyr_jira_mcp.jira_client import (
    JiraClient,
    JiraNotFoundError,
    JiraAuthenticationError,
)


@pytest.mark.asyncio
async def test_get_issue_success(mock_settings, sample_jira_story_dict):
    def handler(request: httpx.Request):
        assert request.url.path == "/rest/api/2/issue/PAY-101"
        assert request.headers.get("Authorization") == "Bearer mock-token-xyz123"
        return httpx.Response(200, json=sample_jira_story_dict)

    client = JiraClient(mock_settings)
    client._get_client = lambda: httpx.AsyncClient(
        base_url=mock_settings.jira_base_url,
        headers=mock_settings.get_auth_headers(),
        transport=httpx.MockTransport(handler),
    )

    issue = await client.get_issue("PAY-101")
    assert issue["key"] == "PAY-101"


@pytest.mark.asyncio
async def test_get_issue_not_found(mock_settings):
    def handler(request: httpx.Request):
        return httpx.Response(404, text="Not Found")

    client = JiraClient(mock_settings)
    client._get_client = lambda: httpx.AsyncClient(
        base_url=mock_settings.jira_base_url,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(JiraNotFoundError):
        await client.get_issue("INVALID-999")


@pytest.mark.asyncio
async def test_create_test_issue(mock_settings):
    def handler(request: httpx.Request):
        assert request.url.path == "/rest/api/2/issue"
        assert request.method == "POST"
        return httpx.Response(201, json={"id": "10999", "key": "PAY-200", "self": "..."})

    client = JiraClient(mock_settings)
    client._get_client = lambda: httpx.AsyncClient(
        base_url=mock_settings.jira_base_url,
        transport=httpx.MockTransport(handler),
    )

    result = await client.create_test_issue(
        project_key="PAY",
        summary="[PAY-101] [Positive] Valid refund check",
        description="Test description",
        priority="High",
        labels=["upi"],
    )
    assert result["key"] == "PAY-200"
    assert result["id"] == "10999"


@pytest.mark.asyncio
async def test_link_issue_to_story(mock_settings):
    def handler(request: httpx.Request):
        assert request.url.path == "/rest/api/2/issueLink"
        return httpx.Response(201)

    client = JiraClient(mock_settings)
    client._get_client = lambda: httpx.AsyncClient(
        base_url=mock_settings.jira_base_url,
        transport=httpx.MockTransport(handler),
    )

    success = await client.link_issue_to_story(
        story_key="PAY-101",
        test_key="PAY-200",
    )
    assert success is True
