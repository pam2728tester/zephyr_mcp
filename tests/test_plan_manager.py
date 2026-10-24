"""Tests for PlanManager: storage, dry-run, and two-phase publishing."""

import pytest
from unittest.mock import AsyncMock
from zephyr_jira_mcp.plan_manager import PlanManager
from zephyr_jira_mcp.models import (
    TestPlanSpec,
    PlanStatus,
)


@pytest.mark.asyncio
async def test_save_and_get_plan(mock_settings, sample_test_case):
    pm = PlanManager(mock_settings)
    plan = TestPlanSpec(
        plan_id="PLAN-PAY-101-TEST1",
        story_key="PAY-101",
        story_summary="Test UPI Story",
        test_cases=[sample_test_case],
    )
    pm.save_plan(plan)

    retrieved = pm.get_plan("PLAN-PAY-101-TEST1")
    assert retrieved is not None
    assert retrieved.story_key == "PAY-101"
    assert len(retrieved.test_cases) == 1


@pytest.mark.asyncio
async def test_publish_dry_run(mock_settings, sample_test_case):
    pm = PlanManager(mock_settings)
    plan = TestPlanSpec(
        plan_id="PLAN-PAY-101-DRY",
        story_key="PAY-101",
        story_summary="Test UPI Story",
        test_cases=[sample_test_case],
    )
    pm.save_plan(plan)

    result = await pm.publish_plan("PLAN-PAY-101-DRY", dry_run=True)
    assert result.is_success is True
    assert result.dry_run is True
    assert result.total_created == 1
    assert result.created_tests[0].status == "DRY_RUN_VALIDATED"
    assert result.created_tests[0].test_key.startswith("PAY-SIM-")


@pytest.mark.asyncio
async def test_publish_live_success(mock_settings, sample_test_case):
    mock_jira = AsyncMock()
    mock_jira.create_test_issue.return_value = {"id": "10999", "key": "PAY-201"}
    mock_jira.link_issue_to_story.return_value = True

    mock_zephyr = AsyncMock()
    mock_zephyr.add_test_steps_batch.return_value = [{"id": 1}, {"id": 2}]

    pm = PlanManager(mock_settings, jira_client=mock_jira, zephyr_client=mock_zephyr)
    plan = TestPlanSpec(
        plan_id="PLAN-PAY-101-LIVE",
        story_key="PAY-101",
        story_summary="Test UPI Story",
        test_cases=[sample_test_case],
    )
    pm.save_plan(plan)

    result = await pm.publish_plan("PLAN-PAY-101-LIVE", dry_run=False)
    assert result.is_success is True
    assert result.total_created == 1
    assert result.created_tests[0].status == "PUBLISHED"
    assert result.created_tests[0].test_key == "PAY-201"
    assert result.created_tests[0].linked_to_story is True

    # Check updated plan in storage
    updated_plan = pm.get_plan("PLAN-PAY-101-LIVE")
    assert updated_plan.status == PlanStatus.PUBLISHED
    assert updated_plan.published_keys == ["PAY-201"]
