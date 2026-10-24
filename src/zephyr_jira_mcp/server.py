"""Model Context Protocol (MCP) Server for Zephyr Squad & Jira Server/DC."""

import json
import logging
from typing import Any, Optional
from mcp.server.mcpserver import MCPServer
from .config import settings
from .jira_client import JiraClient
from .zephyr_client import ZephyrClient
from .story_analyzer import StoryAnalyzer
from .test_synthesizer import TestSynthesizer
from .plan_manager import PlanManager
from .models import (
    PlanStatus,
    PriorityLevel,
    TestCaseSpec,
    TestStepSpec,
    TestType,
)

logger = logging.getLogger("zephyr_jira_mcp")
logging.basicConfig(level=logging.INFO)

# Initialize MCP Server instance
app = MCPServer(
    name="zephyr-jira-mcp",
    version="1.0.0",
    description="Senior Test Engineering MCP for Zephyr Squad Test Case Generation & Jira Traceability",
)

# Shared orchestrators
jira_client = JiraClient(settings)
zephyr_client = ZephyrClient(settings)
plan_manager = PlanManager(settings, jira_client=jira_client, zephyr_client=zephyr_client)


@app.tool()
async def get_jira_story(story_key: str) -> str:
    """Fetch Jira Story details, parsed Acceptance Criteria, and existing linked tests.
    
    Args:
        story_key: Jira issue key (e.g. 'PROJ-101')
    """
    try:
        raw_issue = await jira_client.get_issue(story_key)
        context = StoryAnalyzer.from_jira_issue_dict(raw_issue)
        return context.model_dump_json(indent=2)
    except Exception as exc:
        return json.dumps({
            "error": f"Failed to retrieve Jira Story '{story_key}': {str(exc)}",
            "story_key": story_key,
        }, indent=2)


@app.tool()
async def generate_test_plan(
    story_key: str,
    max_cases: int = 8,
    include_negative: bool = True,
    include_boundary: bool = True,
    include_security: bool = False,
) -> str:
    """Phase 1 (Safe Read-Only): Synthesize QA test cases & traceability matrix from a Jira Story.
    
    Generates structured test cases with preconditions, steps, test data, and expected results.
    Does NOT modify Jira or Zephyr. Returns a reviewable plan_id for Phase 2 publication.
    
    Args:
        story_key: Target Jira Story key (e.g. 'PROJ-101')
        max_cases: Maximum number of test cases to generate (default: 8)
        include_negative: Whether to generate negative test cases (default: True)
        include_boundary: Whether to generate boundary/edge-case tests (default: True)
        include_security: Whether to generate authorization/security tests (default: False)
    """
    try:
        raw_issue = await jira_client.get_issue(story_key)
        story_ctx = StoryAnalyzer.from_jira_issue_dict(raw_issue)

        test_types = [TestType.POSITIVE]
        if include_negative:
            test_types.append(TestType.NEGATIVE)
        if include_boundary:
            test_types.append(TestType.BOUNDARY)
        if include_security:
            test_types.append(TestType.SECURITY)

        plan = TestSynthesizer.synthesize_test_plan(
            story=story_ctx,
            include_types=test_types,
            max_cases=max_cases,
        )

        # Cache the plan for human review
        plan_manager.save_plan(plan)

        summary_output = {
            "plan_id": plan.plan_id,
            "status": plan.status.value,
            "story_key": plan.story_key,
            "story_summary": plan.story_summary,
            "total_test_cases": len(plan.test_cases),
            "unmapped_criteria": plan.unmapped_criteria,
            "traceability_matrix": [t.model_dump() for t in plan.traceability_matrix],
            "test_cases": [tc.model_dump() for tc in plan.test_cases],
            "next_step": (
                f"Review the test plan. To execute writes into Jira & Zephyr, call "
                f"'publish_test_plan(plan_id=\"{plan.plan_id}\", dry_run=False)'"
            ),
        }
        return json.dumps(summary_output, indent=2)

    except Exception as exc:
        return json.dumps({
            "error": f"Failed to generate test plan for '{story_key}': {str(exc)}",
            "story_key": story_key,
        }, indent=2)


@app.tool()
async def review_test_plan(plan_id: str) -> str:
    """Inspect an existing test plan by its Plan ID before committing writes.
    
    Args:
        plan_id: The plan ID returned by generate_test_plan (e.g. 'PLAN-PROJ-101-abcd1234')
    """
    plan = plan_manager.get_plan(plan_id)
    if not plan:
        return json.dumps({
            "error": f"Test plan '{plan_id}' not found.",
            "available_plans": plan_manager.list_plans(),
        }, indent=2)
    return plan.model_dump_json(indent=2)


@app.tool()
async def publish_test_plan(plan_id: str, dry_run: bool = False) -> str:
    """Phase 2 (Controlled Execution): Publish approved test plan to Jira Server & Zephyr ZAPI.
    
    Creates 'Test' issues in Jira, posts test steps to Zephyr ZAPI, and links them to the Story.
    
    Args:
        plan_id: Plan ID to publish
        dry_run: When True, simulates the write actions without calling remote APIs (default: False)
    """
    try:
        result = await plan_manager.publish_plan(plan_id=plan_id, dry_run=dry_run)
        return result.model_dump_json(indent=2)
    except Exception as exc:
        return json.dumps({
            "error": f"Publication failed for plan '{plan_id}': {str(exc)}",
            "plan_id": plan_id,
            "is_success": False,
        }, indent=2)


@app.tool()
async def create_single_test_case(
    story_key: str,
    title: str,
    summary: str,
    description: str,
    preconditions: str,
    steps: list[dict[str, str]],
    priority: str = "Medium",
    dry_run: bool = False,
) -> str:
    """Directly create and link an ad-hoc custom Zephyr test case to a Jira Story.
    
    Args:
        story_key: Target Jira Story key (e.g. 'PROJ-101')
        title: Test case title
        summary: Jira Test issue summary
        description: Test objective and scope
        preconditions: Prerequisites or environment state
        steps: List of step dicts with keys 'step', 'data', and 'result'
        priority: Priority ('Highest', 'High', 'Medium', 'Low', 'Lowest')
        dry_run: Simulate without executing network writes
    """
    try:
        parsed_priority = PriorityLevel(priority) if priority in PriorityLevel._value2member_map_ else PriorityLevel.MEDIUM
        test_steps = [
            TestStepSpec(
                step=s.get("step", ""),
                data=s.get("data", ""),
                result=s.get("result", ""),
            )
            for s in steps
        ]

        spec = TestCaseSpec(
            title=title,
            summary=summary,
            description=description,
            priority=parsed_priority,
            preconditions=preconditions,
            steps=test_steps,
            labels=["manual-mcp"],
        )
        spec.logical_hash = spec.compute_hash(story_key)

        result = await plan_manager.create_single_test_case(
            story_key=story_key,
            test_case=spec,
            dry_run=dry_run,
        )
        return result.model_dump_json(indent=2)
    except Exception as exc:
        return json.dumps({
            "error": f"Failed to create test case for '{story_key}': {str(exc)}",
            "story_key": story_key,
        }, indent=2)


@app.tool()
async def verify_story_traceability(story_key: str) -> str:
    """Audit test coverage and verified links between a Jira Story and Zephyr Tests.
    
    Args:
        story_key: Jira issue key (e.g. 'PROJ-101')
    """
    try:
        raw_issue = await jira_client.get_issue(story_key)
        context = StoryAnalyzer.from_jira_issue_dict(raw_issue)

        linked_details = []
        for test_key in context.linked_tests:
            try:
                test_issue = await jira_client.get_issue(test_key)
                test_id = str(test_issue.get("id", ""))
                steps = await zephyr_client.get_test_steps(test_id)
                linked_details.append({
                    "test_key": test_key,
                    "summary": (test_issue.get("fields") or {}).get("summary", ""),
                    "steps_count": len(steps),
                })
            except Exception as err:
                linked_details.append({
                    "test_key": test_key,
                    "error": str(err),
                })

        report = {
            "story_key": story_key,
            "story_summary": context.summary,
            "acceptance_criteria_count": len(context.acceptance_criteria),
            "linked_tests_count": len(context.linked_tests),
            "linked_tests": linked_details,
            "coverage_adequate": len(context.linked_tests) > 0,
        }
        return json.dumps(report, indent=2)
    except Exception as exc:
        return json.dumps({
            "error": f"Traceability verification failed for '{story_key}': {str(exc)}",
            "story_key": story_key,
        }, indent=2)


@app.resource("zephyr://plans/{plan_id}")
async def get_plan_resource(plan_id: str) -> str:
    """Read a saved test plan as a JSON resource."""
    plan = plan_manager.get_plan(plan_id)
    if not plan:
        return json.dumps({"error": f"Plan '{plan_id}' not found."})
    return plan.model_dump_json(indent=2)


@app.prompt("zephyr-test-engineering-plan")
def zephyr_test_engineering_prompt(story_key: str) -> str:
    """Prompt template for QA engineers planning Zephyr test cases."""
    return f"""You are a Senior Principal QA & Test Automation Architect.
Task: Inspect Jira Story '{story_key}', extract every acceptance criterion, and generate exhaustive test cases with Zephyr steps.

Engineering Requirements:
1. Extract and validate each Acceptance Criterion (AC-1, AC-2, etc.).
2. Generate Positive/Happy Path tests, Negative validation tests, and Boundary Value tests.
3. For each test, provide:
   - Clear Title & Jira Summary
   - Preconditions
   - Sequential steps with explicit 'step', 'data', and deterministic 'result'
4. Verify complete traceability (no unmapped criteria).
5. Review the plan with the user before committing writes to Jira and Zephyr ZAPI.
"""


def main():
    """Main entrypoint for running the MCP server over stdio."""
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
