"""Domain models and schemas for Jira & Zephyr test management."""

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class TestType(str, Enum):
    __test__ = False
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    BOUNDARY = "BOUNDARY"
    SECURITY = "SECURITY"
    REGRESSION = "REGRESSION"
    EDGE_CASE = "EDGE_CASE"


class PriorityLevel(str, Enum):
    HIGHEST = "Highest"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    LOWEST = "Lowest"


class PlanStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"


class TestStepSpec(BaseModel):
    """Specification of an individual Zephyr test step."""
    __test__ = False
    step: str = Field(description="Action/instruction to execute in this step")
    data: str = Field(default="", description="Test data or inputs required for this step")
    result: str = Field(description="Expected outcome or deterministic assertion for this step")


class AcceptanceCriterion(BaseModel):
    """Individual parsed acceptance criterion from a Jira story."""
    id: str = Field(description="Unique identifier (e.g. AC-1, AC-2)")
    text: str = Field(description="Text description of the criterion or BDD scenario")
    is_bdd: bool = Field(default=False, description="Whether criterion follows Given/When/Then structure")


class JiraStoryContext(BaseModel):
    """Normalized representation of a Jira Story."""
    key: str = Field(description="Jira issue key, e.g. PROJ-101")
    id: str = Field(description="Jira internal issue ID, e.g. 10023")
    summary: str = Field(description="Story summary/title")
    description: str = Field(default="", description="Story description (plain text/markdown)")
    status: str = Field(default="Open", description="Workflow status")
    components: list[str] = Field(default_factory=list, description="Associated components")
    labels: list[str] = Field(default_factory=list, description="Labels")
    acceptance_criteria: list[AcceptanceCriterion] = Field(
        default_factory=list, description="Parsed acceptance criteria"
    )
    linked_tests: list[str] = Field(
        default_factory=list, description="Keys of already linked test cases"
    )


class TestCaseSpec(BaseModel):
    """Specification of a Zephyr test case to be created in Jira."""
    __test__ = False
    title: str = Field(description="Concise, descriptive test case title")
    summary: str = Field(description="Jira issue summary (prefixed e.g. [Test] ...)")
    description: str = Field(default="", description="Detailed test objective and scope")
    test_type: TestType = Field(default=TestType.POSITIVE, description="Category of testing")
    priority: PriorityLevel = Field(default=PriorityLevel.MEDIUM, description="Test execution priority")
    preconditions: str = Field(default="", description="Prerequisite system state or test setup")
    steps: list[TestStepSpec] = Field(default_factory=list, description="Sequential test steps")
    covered_criteria_ids: list[str] = Field(
        default_factory=list, description="IDs of acceptance criteria covered by this test"
    )
    labels: list[str] = Field(default_factory=list, description="Jira issue labels")
    components: list[str] = Field(default_factory=list, description="Jira component names")
    logical_hash: str = Field(default="", description="Deterministic SHA256 idempotency hash")

    def compute_hash(self, story_key: str) -> str:
        """Calculate a deterministic hash based on story key, title, and steps."""
        step_fingerprint = "|".join(
            f"{s.step}:{s.data}:{s.result}" for s in self.steps
        )
        raw = f"{story_key}::{self.title}::{self.preconditions}::{step_fingerprint}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class TraceabilityEntry(BaseModel):
    """Mapping between an acceptance criterion and corresponding test cases."""
    criterion_id: str
    criterion_text: str
    test_titles: list[str]
    covered: bool


class TestPlanSpec(BaseModel):
    """Two-phase test plan container for human-in-the-loop review."""
    __test__ = False
    plan_id: str = Field(description="Unique plan identifier")
    story_key: str = Field(description="Target Jira Story issue key")
    story_summary: str = Field(description="Story summary")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: PlanStatus = Field(default=PlanStatus.PENDING_REVIEW)
    test_cases: list[TestCaseSpec] = Field(default_factory=list)
    unmapped_criteria: list[str] = Field(
        default_factory=list, description="Criteria not addressed by any test case"
    )
    traceability_matrix: list[TraceabilityEntry] = Field(default_factory=list)
    published_keys: list[str] = Field(
        default_factory=list, description="Keys of created Jira test issues if published"
    )


class CreatedTestRecord(BaseModel):
    """Record of an individual created Jira/Zephyr test case."""
    test_key: str
    issue_id: str
    summary: str
    steps_count: int
    linked_to_story: bool
    status: str
    error: Optional[str] = None


class PublishResult(BaseModel):
    """Result of publishing an approved test plan to Jira Server & Zephyr ZAPI."""
    plan_id: str
    story_key: str
    dry_run: bool
    total_requested: int
    total_created: int
    created_tests: list[CreatedTestRecord] = Field(default_factory=list)
    skipped_existing: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    is_success: bool = True
