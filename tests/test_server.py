"""Tests for MCPServer tool functions in zephyr_jira_mcp.server."""

import json
import pytest
from unittest.mock import AsyncMock, patch
import zephyr_jira_mcp.server as srv


@pytest.mark.asyncio
async def test_get_jira_story_tool(sample_jira_story_dict):
    with patch.object(srv.jira_client, "get_issue", AsyncMock(return_value=sample_jira_story_dict)):
        result_str = await srv.get_jira_story("PAY-101")
        data = json.loads(result_str)
        assert data["key"] == "PAY-101"
        assert len(data["acceptance_criteria"]) == 4


@pytest.mark.asyncio
async def test_generate_test_plan_tool(sample_jira_story_dict):
    with patch.object(srv.jira_client, "get_issue", AsyncMock(return_value=sample_jira_story_dict)):
        result_str = await srv.generate_test_plan(
            story_key="PAY-101",
            max_cases=6,
            include_negative=True,
            include_boundary=True,
        )
        data = json.loads(result_str)
        assert data["story_key"] == "PAY-101"
        assert data["status"] == "PENDING_REVIEW"
        assert data["total_test_cases"] > 0
        assert "plan_id" in data

        # Review plan
        plan_id = data["plan_id"]
        review_str = await srv.review_test_plan(plan_id)
        review_data = json.loads(review_str)
        assert review_data["plan_id"] == plan_id


@pytest.mark.asyncio
async def test_publish_test_plan_tool_dry_run(sample_jira_story_dict):
    with patch.object(srv.jira_client, "get_issue", AsyncMock(return_value=sample_jira_story_dict)):
        plan_str = await srv.generate_test_plan(story_key="PAY-101", max_cases=2)
        plan_data = json.loads(plan_str)
        plan_id = plan_data["plan_id"]

        pub_str = await srv.publish_test_plan(plan_id=plan_id, dry_run=True)
        pub_data = json.loads(pub_str)
        assert pub_data["is_success"] is True
        assert pub_data["dry_run"] is True
        assert pub_data["total_created"] == 2


@pytest.mark.asyncio
async def test_create_single_test_case_tool():
    step_input = [
        {"step": "Enter amount 500", "data": "amount=500", "result": "Form valid"},
        {"step": "Click submit", "data": "Click", "result": "Processing initiated"},
    ]
    result_str = await srv.create_single_test_case(
        story_key="PAY-101",
        title="Verify Basic Payment",
        summary="[PAY-101] Valid payment submission",
        description="Check payment flow",
        preconditions="User has funds",
        steps=step_input,
        priority="High",
        dry_run=True,
    )
    data = json.loads(result_str)
    assert data["status"] == "DRY_RUN_VALIDATED"
    assert data["steps_count"] == 2


@pytest.mark.asyncio
async def test_verify_story_traceability_tool(sample_jira_story_dict):
    with patch.object(srv.jira_client, "get_issue", AsyncMock(return_value=sample_jira_story_dict)), \
         patch.object(srv.zephyr_client, "get_test_steps", AsyncMock(return_value=[{"id": 1}])):
        result_str = await srv.verify_story_traceability("PAY-101")
        data = json.loads(result_str)
        assert data["story_key"] == "PAY-101"
        assert data["linked_tests_count"] == 1
        assert data["coverage_adequate"] is True
