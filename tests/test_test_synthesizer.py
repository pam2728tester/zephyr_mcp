"""Tests for TestSynthesizer: QA synthesis, coverage, and idempotency."""

from zephyr_jira_mcp.test_synthesizer import TestSynthesizer
from zephyr_jira_mcp.models import TestType, PriorityLevel


def test_synthesize_test_plan_coverage(sample_story_context):
    plan = TestSynthesizer.synthesize_test_plan(
        story=sample_story_context,
        include_types=[TestType.POSITIVE, TestType.NEGATIVE],
        max_cases=10,
    )

    assert plan.story_key == "PAY-101"
    assert plan.plan_id.startswith("PLAN-PAY-101-")
    assert len(plan.test_cases) > 0

    # Ensure all 3 ACs in sample_story_context are mapped in traceability matrix
    assert len(plan.traceability_matrix) == 3
    assert plan.unmapped_criteria == []

    # Check first test case anatomy
    first_tc = plan.test_cases[0]
    assert first_tc.priority in (PriorityLevel.HIGH, PriorityLevel.MEDIUM)
    assert len(first_tc.steps) >= 2
    for step in first_tc.steps:
        assert step.step != ""
        assert step.result != ""

    # Check idempotency hash
    assert len(first_tc.logical_hash) == 16


def test_idempotency_hash_stability(sample_story_context):
    plan1 = TestSynthesizer.synthesize_test_plan(sample_story_context)
    plan2 = TestSynthesizer.synthesize_test_plan(sample_story_context)

    # The logical hash for identical test case titles/steps should be identical
    hashes1 = [c.logical_hash for c in plan1.test_cases]
    hashes2 = [c.logical_hash for c in plan2.test_cases]
    assert hashes1 == hashes2


def test_fallback_synthesis_when_no_criteria(sample_story_context):
    # Story with empty acceptance criteria
    sample_story_context.acceptance_criteria = []
    plan = TestSynthesizer.synthesize_test_plan(sample_story_context)

    assert len(plan.test_cases) >= 1
    assert "PAY-101" in plan.test_cases[0].summary
