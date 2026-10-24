"""Senior Test Engineering synthesis engine: creates high-rigor Zephyr test cases."""

import uuid
from typing import Optional
from .models import (
    AcceptanceCriterion,
    JiraStoryContext,
    PriorityLevel,
    TestPlanSpec,
    TestCaseSpec,
    TestStepSpec,
    TestType,
    TraceabilityEntry,
)


class TestSynthesizer:
    """Transforms Jira stories and acceptance criteria into structured Zephyr test cases."""

    @classmethod
    def synthesize_test_plan(
        cls,
        story: JiraStoryContext,
        include_types: Optional[list[TestType]] = None,
        max_cases: int = 10,
    ) -> TestPlanSpec:
        """Generate a complete test plan with positive, negative, and boundary cases."""
        if include_types is None:
            include_types = [
                TestType.POSITIVE,
                TestType.NEGATIVE,
                TestType.BOUNDARY,
                TestType.EDGE_CASE,
            ]

        test_cases: list[TestCaseSpec] = []
        covered_criteria_ids: set[str] = set()

        # If story has specific acceptance criteria, generate focused cases per criterion
        if story.acceptance_criteria:
            for ac in story.acceptance_criteria:
                cases_for_ac = cls._generate_cases_for_criterion(story, ac, include_types)
                for c in cases_for_ac:
                    if len(test_cases) >= max_cases:
                        break
                    test_cases.append(c)
                    covered_criteria_ids.update(c.covered_criteria_ids)
                if len(test_cases) >= max_cases:
                    break
        else:
            # Fallback when story description lacks explicit AC list
            fallback_cases = cls._generate_generic_story_cases(story, include_types)
            test_cases.extend(fallback_cases[:max_cases])

        # Compute traceability matrix
        matrix: list[TraceabilityEntry] = []
        unmapped: list[str] = []
        all_ac_ids = {ac.id for ac in story.acceptance_criteria}

        for ac in story.acceptance_criteria:
            matching_titles = [
                tc.title for tc in test_cases if ac.id in tc.covered_criteria_ids
            ]
            is_covered = len(matching_titles) > 0
            if not is_covered:
                unmapped.append(ac.id)
            matrix.append(
                TraceabilityEntry(
                    criterion_id=ac.id,
                    criterion_text=ac.text,
                    test_titles=matching_titles,
                    covered=is_covered,
                )
            )

        plan_id = f"PLAN-{story.key}-{uuid.uuid4().hex[:8]}"

        return TestPlanSpec(
            plan_id=plan_id,
            story_key=story.key,
            story_summary=story.summary,
            test_cases=test_cases,
            unmapped_criteria=unmapped,
            traceability_matrix=matrix,
        )

    @classmethod
    def _generate_cases_for_criterion(
        cls,
        story: JiraStoryContext,
        ac: AcceptanceCriterion,
        include_types: list[TestType],
    ) -> list[TestCaseSpec]:
        """Synthesize positive and negative test cases for an individual Acceptance Criterion."""
        cases: list[TestCaseSpec] = []

        # 1. Happy Path / Positive Scenario
        if TestType.POSITIVE in include_types:
            pos_case = TestCaseSpec(
                title=f"Verify {ac.id} - Happy Path: {ac.text[:60]}...",
                summary=f"[{story.key}] [Positive] {ac.text[:70]}",
                description=(
                    f"Objective: Validate positive execution of requirement {ac.id} from story {story.key}.\n\n"
                    f"Target Criterion: {ac.text}"
                ),
                test_type=TestType.POSITIVE,
                priority=PriorityLevel.HIGH,
                preconditions=(
                    f"1. User is authenticated with active session and appropriate permissions.\n"
                    f"2. System is in healthy, stable initial state for {story.summary}.\n"
                    f"3. Prerequisites for {story.key} are provisioned."
                ),
                steps=[
                    TestStepSpec(
                        step=f"Navigate to feature area for '{story.summary}'.",
                        data="Valid authenticated user credentials",
                        result="Feature view or endpoint is rendered successfully with HTTP 200.",
                    ),
                    TestStepSpec(
                        step=f"Execute primary action: {ac.text}.",
                        data="Valid production-equivalent test payload",
                        result="Action succeeds without errors or unexpected latency.",
                    ),
                    TestStepSpec(
                        step="Verify system state and persistent changes.",
                        data="Query persistence / database / UI inspection",
                        result="Entities are updated correctly and confirmation is presented.",
                    ),
                ],
                covered_criteria_ids=[ac.id],
                labels=story.labels + ["automated-mcp", "positive"],
                components=story.components,
            )
            pos_case.logical_hash = pos_case.compute_hash(story.key)
            cases.append(pos_case)

        # 2. Negative / Boundary / Edge Case
        if TestType.NEGATIVE in include_types or TestType.BOUNDARY in include_types:
            neg_case = TestCaseSpec(
                title=f"Verify {ac.id} - Negative/Boundary: Validation & Error Handling",
                summary=f"[{story.key}] [Negative] Reject invalid input for {ac.id}",
                description=(
                    f"Objective: Verify system rejects malformed input and boundary violations for {ac.id}.\n\n"
                    f"Target Criterion: {ac.text}"
                ),
                test_type=TestType.NEGATIVE,
                priority=PriorityLevel.MEDIUM,
                preconditions=(
                    f"1. User is logged in to verify authorization boundaries.\n"
                    f"2. Target resources for {story.key} are accessible."
                ),
                steps=[
                    TestStepSpec(
                        step=f"Attempt to execute {ac.text} with invalid, empty, or out-of-bound parameters.",
                        data="Invalid inputs: null values, special characters (<script>), oversized payload",
                        result="Request is rejected; validation errors are returned immediately.",
                    ),
                    TestStepSpec(
                        step="Verify user-facing error message and system integrity.",
                        data="Inspect UI alert or HTTP status code (400 Bad Request / 422 Unprocessable)",
                        result="Clear, localized, non-leaking error message is displayed. No data corruption occurs.",
                    ),
                ],
                covered_criteria_ids=[ac.id],
                labels=story.labels + ["automated-mcp", "negative"],
                components=story.components,
            )
            neg_case.logical_hash = neg_case.compute_hash(story.key)
            cases.append(neg_case)

        return cases

    @classmethod
    def _generate_generic_story_cases(
        cls,
        story: JiraStoryContext,
        include_types: list[TestType],
    ) -> list[TestCaseSpec]:
        """Generate baseline test cases when explicit ACs could not be extracted."""
        cases: list[TestCaseSpec] = []

        if TestType.POSITIVE in include_types:
            pos_case = TestCaseSpec(
                title=f"Verify End-to-End Workflow: {story.summary}",
                summary=f"[{story.key}] [E2E] Baseline positive workflow",
                description=f"Validate end-to-end functionality for Jira Story {story.key}: {story.summary}",
                test_type=TestType.POSITIVE,
                priority=PriorityLevel.HIGH,
                preconditions="Standard test environment active; required user roles assigned.",
                steps=[
                    TestStepSpec(
                        step=f"Initialize test session for {story.key}.",
                        data="Role: Standard Authorized User",
                        result="Access granted; dashboard/endpoint responds with 200 OK.",
                    ),
                    TestStepSpec(
                        step=f"Perform core workflow operations described in: {story.summary}.",
                        data="Standard valid test dataset",
                        result="Workflow completes with success indicators and persistent updates.",
                    ),
                ],
                covered_criteria_ids=[],
                labels=story.labels + ["automated-mcp"],
                components=story.components,
            )
            pos_case.logical_hash = pos_case.compute_hash(story.key)
            cases.append(pos_case)

        if TestType.SECURITY in include_types or TestType.NEGATIVE in include_types:
            sec_case = TestCaseSpec(
                title=f"Verify Authorization and Data Protection: {story.summary}",
                summary=f"[{story.key}] [Security] Unauthorized access rejection",
                description=f"Verify that unauthorized users or revoked sessions cannot execute operations in {story.key}.",
                test_type=TestType.SECURITY,
                priority=PriorityLevel.HIGH,
                preconditions="User with no permissions or expired session token.",
                steps=[
                    TestStepSpec(
                        step="Attempt to trigger operations with missing or expired authentication.",
                        data="Authorization: Bearer <expired/invalid>",
                        result="Operation blocked with HTTP 401 Unauthorized or 403 Forbidden.",
                    ),
                ],
                covered_criteria_ids=[],
                labels=story.labels + ["automated-mcp", "security"],
                components=story.components,
            )
            sec_case.logical_hash = sec_case.compute_hash(story.key)
            cases.append(sec_case)

        return cases
