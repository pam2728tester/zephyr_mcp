"""Pytest fixtures and mock data for Zephyr Jira MCP test suite."""

import pytest
from zephyr_jira_mcp.config import Settings
from zephyr_jira_mcp.models import (
    AcceptanceCriterion,
    JiraStoryContext,
    TestCaseSpec,
    TestStepSpec,
    TestType,
)


@pytest.fixture
def mock_settings(tmp_path):
    """Provides isolated test settings with temporary storage directory."""
    return Settings(
        jira_base_url="https://jira.mock.internal",
        jira_pat="mock-token-xyz123",
        jira_test_issue_type="Test",
        jira_test_link_type="Tests",
        default_project_key="PAY",
        storage_dir=tmp_path / "zephyr_storage",
    )


@pytest.fixture
def sample_jira_story_dict():
    """Raw Jira issue JSON matching Jira Server/DC response format."""
    return {
        "id": "10550",
        "key": "PAY-101",
        "fields": {
            "summary": "Implement Instant UPI Refund Processing",
            "description": (
                "As a customer, I want my failed transactions to trigger an instant UPI refund.\n\n"
                "Acceptance Criteria:\n"
                "1. If bank confirms transaction failure, refund must be initiated within 5 seconds.\n"
                "2. Given a user initiates refund, when UPI VPA is valid, then initiate transfer and send SMS.\n"
                "3. Refund amount cannot exceed the original transaction value or be negative.\n"
                "4. An idempotent transaction ID must prevent double refunds on retry.\n\n"
                "Out of Scope:\n"
                "- International card refunds."
            ),
            "status": {"name": "In Progress"},
            "components": [{"name": "Payments"}, {"name": "RefundGateway"}],
            "labels": ["upi", "refunds", "fintech"],
            "issuelinks": [
                {
                    "id": "201",
                    "inwardIssue": {
                        "id": "10800",
                        "key": "PAY-50",
                        "fields": {"issuetype": {"name": "Test"}},
                    },
                }
            ],
        },
    }


@pytest.fixture
def sample_story_context():
    """Parsed JiraStoryContext fixture."""
    return JiraStoryContext(
        key="PAY-101",
        id="10550",
        summary="Implement Instant UPI Refund Processing",
        description="Core UPI Refund logic",
        status="In Progress",
        components=["Payments"],
        labels=["upi", "refunds"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-1",
                text="Refund initiated within 5 seconds of failure confirmation.",
                is_bdd=False,
            ),
            AcceptanceCriterion(
                id="AC-2",
                text="Given valid UPI VPA, when refund is initiated, transfer and send SMS.",
                is_bdd=True,
            ),
            AcceptanceCriterion(
                id="AC-3",
                text="Refund amount cannot exceed original transaction value or be negative.",
                is_bdd=False,
            ),
        ],
        linked_tests=["PAY-50"],
    )


@pytest.fixture
def sample_test_case():
    """Pre-built TestCaseSpec for publishing tests."""
    tc = TestCaseSpec(
        title="Verify Instant UPI Refund - Boundary Value Check",
        summary="[PAY-101] [Boundary] Refund amount upper and lower bounds",
        description="Ensure negative amounts and amounts exceeding original are rejected.",
        test_type=TestType.BOUNDARY,
        preconditions="Active payment account with verified balance.",
        steps=[
            TestStepSpec(
                step="Submit refund request with amount equal to -1.00.",
                data="amount: -1.00",
                result="HTTP 400 Bad Request with validation error 'Amount must be positive'.",
            ),
            TestStepSpec(
                step="Submit refund request with amount exceeding transaction total.",
                data="amount: 999999.00 (original: 500.00)",
                result="HTTP 422 Unprocessable with error 'Refund exceeds transaction amount'.",
            ),
        ],
        covered_criteria_ids=["AC-3"],
        labels=["automated-mcp", "boundary"],
        components=["Payments"],
    )
    tc.logical_hash = tc.compute_hash("PAY-101")
    return tc
