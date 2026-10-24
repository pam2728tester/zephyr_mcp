"""Test Plan persistence and Two-Phase publishing orchestrator."""

import json
import logging
from pathlib import Path
from typing import Optional
from .config import Settings, settings
from .jira_client import JiraClient
from .zephyr_client import ZephyrClient
from .models import (
    CreatedTestRecord,
    PlanStatus,
    PublishResult,
    TestCaseSpec,
    TestPlanSpec,
)

logger = logging.getLogger(__name__)


class PlanManager:
    """Orchestrates test plan caching, approval, and execution into Jira & Zephyr."""

    def __init__(
        self,
        config: Optional[Settings] = None,
        jira_client: Optional[JiraClient] = None,
        zephyr_client: Optional[ZephyrClient] = None,
    ):
        self.cfg = config or settings
        self.jira = jira_client or JiraClient(self.cfg)
        self.zephyr = zephyr_client or ZephyrClient(self.cfg)
        self.plans_dir = self.cfg.storage_dir / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self._memory_cache: dict[str, TestPlanSpec] = {}

    def save_plan(self, plan: TestPlanSpec) -> None:
        """Persist a test plan to disk and memory cache."""
        self._memory_cache[plan.plan_id] = plan
        file_path = self.plans_dir / f"{plan.plan_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(plan.model_dump_json(indent=2))

    def get_plan(self, plan_id: str) -> Optional[TestPlanSpec]:
        """Retrieve a stored test plan by its ID."""
        if plan_id in self._memory_cache:
            return self._memory_cache[plan_id]

        file_path = self.plans_dir / f"{plan_id}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                plan = TestPlanSpec.model_validate(data)
                self._memory_cache[plan_id] = plan
                return plan
        return None

    def list_plans(self) -> list[str]:
        """List all available plan IDs."""
        disk_ids = [p.stem for p in self.plans_dir.glob("*.json")]
        all_ids = set(disk_ids).union(self._memory_cache.keys())
        return sorted(list(all_ids))

    async def publish_plan(self, plan_id: str, dry_run: bool = False) -> PublishResult:
        """Publish an approved test plan: creates Jira Test issues, adds ZAPI steps, and links to Story."""
        plan = self.get_plan(plan_id)
        if not plan:
            return PublishResult(
                plan_id=plan_id,
                story_key="",
                dry_run=dry_run,
                total_requested=0,
                total_created=0,
                errors=[f"Plan with ID '{plan_id}' does not exist."],
                is_success=False,
            )

        # Extract project key from Story Key (e.g. "PROJ-123" -> "PROJ")
        project_key = plan.story_key.split("-")[0] if "-" in plan.story_key else (self.cfg.default_project_key or "TEST")

        created_records: list[CreatedTestRecord] = []
        skipped_existing: list[str] = []
        errors: list[str] = []

        for idx, tc in enumerate(plan.test_cases, start=1):
            if dry_run:
                # Dry run: simulate generation without Jira/Zephyr network mutations
                simulated_key = f"{project_key}-SIM-{idx}"
                simulated_id = f"999{idx:02d}"
                created_records.append(
                    CreatedTestRecord(
                        test_key=simulated_key,
                        issue_id=simulated_id,
                        summary=tc.summary,
                        steps_count=len(tc.steps),
                        linked_to_story=True,
                        status="DRY_RUN_VALIDATED",
                    )
                )
                continue

            try:
                # 1. Create Jira Issue of type Test
                created_issue = await self.jira.create_test_issue(
                    project_key=project_key,
                    summary=tc.summary,
                    description=tc.description,
                    priority=tc.priority.value,
                    labels=tc.labels,
                    components=tc.components,
                )
                test_key = created_issue.get("key", "")
                issue_id = str(created_issue.get("id", ""))

                # 2. Add Test Steps via Zephyr ZAPI
                if tc.steps and issue_id:
                    await self.zephyr.add_test_steps_batch(
                        issue_id=issue_id,
                        steps=tc.steps,
                    )

                # 3. Create Bidirectional Link to Jira Story
                linked = await self.jira.link_issue_to_story(
                    story_key=plan.story_key,
                    test_key=test_key,
                )

                created_records.append(
                    CreatedTestRecord(
                        test_key=test_key,
                        issue_id=issue_id,
                        summary=tc.summary,
                        steps_count=len(tc.steps),
                        linked_to_story=linked,
                        status="PUBLISHED",
                    )
                )
            except Exception as exc:
                err_msg = f"Failed to publish test '{tc.title}': {exc}"
                logger.error(err_msg, exc_info=True)
                errors.append(err_msg)
                created_records.append(
                    CreatedTestRecord(
                        test_key="",
                        issue_id="",
                        summary=tc.summary,
                        steps_count=len(tc.steps),
                        linked_to_story=False,
                        status="FAILED",
                        error=str(exc),
                    )
                )

        if not dry_run:
            plan.status = PlanStatus.PUBLISHED if not errors else PlanStatus.APPROVED
            plan.published_keys = [r.test_key for r in created_records if r.test_key]
            self.save_plan(plan)

        return PublishResult(
            plan_id=plan_id,
            story_key=plan.story_key,
            dry_run=dry_run,
            total_requested=len(plan.test_cases),
            total_created=len([r for r in created_records if r.status in ("PUBLISHED", "DRY_RUN_VALIDATED")]),
            created_tests=created_records,
            skipped_existing=skipped_existing,
            errors=errors,
            is_success=(len(errors) == 0),
        )

    async def create_single_test_case(
        self,
        story_key: str,
        test_case: TestCaseSpec,
        dry_run: bool = False,
    ) -> CreatedTestRecord:
        """Create and link a single custom test case directly."""
        project_key = story_key.split("-")[0] if "-" in story_key else (self.cfg.default_project_key or "TEST")

        if dry_run:
            return CreatedTestRecord(
                test_key=f"{project_key}-SIM-1",
                issue_id="99901",
                summary=test_case.summary,
                steps_count=len(test_case.steps),
                linked_to_story=True,
                status="DRY_RUN_VALIDATED",
            )

        created_issue = await self.jira.create_test_issue(
            project_key=project_key,
            summary=test_case.summary,
            description=test_case.description,
            priority=test_case.priority.value,
            labels=test_case.labels,
            components=test_case.components,
        )
        test_key = created_issue.get("key", "")
        issue_id = str(created_issue.get("id", ""))

        if test_case.steps and issue_id:
            await self.zephyr.add_test_steps_batch(
                issue_id=issue_id,
                steps=test_case.steps,
            )

        linked = await self.jira.link_issue_to_story(
            story_key=story_key,
            test_key=test_key,
        )

        return CreatedTestRecord(
            test_key=test_key,
            issue_id=issue_id,
            summary=test_case.summary,
            steps_count=len(test_case.steps),
            linked_to_story=linked,
            status="PUBLISHED",
        )
