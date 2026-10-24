"""Jira Story parser and Acceptance Criteria extractor."""

import re
from typing import Any
from .models import AcceptanceCriterion, JiraStoryContext


class StoryAnalyzer:
    """Extracts requirements, ACs, and metadata from Jira Story issues."""

    AC_PATTERNS = [
        re.compile(r"(?:acceptance\s+criteria|a/?c)\s*[:\-\n](.+?)(?=\n\s*(?:notes|out\s+of\s+scope|technical|dependencies|definition\s+of\s+done|\Z))", re.IGNORECASE | re.DOTALL),
        re.compile(r"scenario\s*[:\-\n](.+?)(?=\n\s*scenario|\Z)", re.IGNORECASE | re.DOTALL),
    ]

    BDD_PATTERN = re.compile(
        r"^\s*scenario:|\bgiven\b.*\bwhen\b|\bwhen\b.*\bthen\b|\bgiven\b.*\bthen\b",
        re.IGNORECASE,
    )

    @staticmethod
    def extract_text_from_jira_description(description: Any) -> str:
        """Handle Jira description which may be string or ADF (Atlassian Document Format)."""
        if not description:
            return ""
        if isinstance(description, str):
            return description
        if isinstance(description, dict):
            # Traverse ADF
            return StoryAnalyzer._parse_adf_node(description)
        return str(description)

    @staticmethod
    def _parse_adf_node(node: dict[str, Any]) -> str:
        """Recursively extract plain text from ADF json structure."""
        text_parts = []
        node_type = node.get("type", "")
        if node_type == "text":
            return node.get("text", "")
        if node_type == "hardBreak":
            return "\n"

        content = node.get("content", [])
        for child in content:
            if isinstance(child, dict):
                text_parts.append(StoryAnalyzer._parse_adf_node(child))

        joined = "".join(text_parts)
        if node_type in ("paragraph", "heading"):
            return joined + "\n"
        if node_type == "listItem":
            return f"- {joined}\n"
        return joined

    @classmethod
    def parse_acceptance_criteria(cls, raw_text: str) -> list[AcceptanceCriterion]:
        """Extract individual criteria points or BDD blocks from story text."""
        criteria: list[AcceptanceCriterion] = []
        if not raw_text.strip():
            return criteria

        # 1. Search for dedicated AC block
        ac_section = ""
        for pattern in cls.AC_PATTERNS:
            match = pattern.search(raw_text)
            if match:
                ac_section = match.group(1).strip()
                break

        target_text = ac_section if ac_section else raw_text

        # 2. Extract items: bullet points, numbered lists, or BDD blocks
        lines = [line.strip() for line in target_text.splitlines() if line.strip()]

        current_block: list[str] = []
        criterion_idx = 1

        for line in lines:
            # Check for bullet or numbered prefix (e.g., "1.", "1)", "*", "-", "#")
            is_item_start = bool(re.match(r"^(\d+[\.\)]|[\*\-\#])\s+", line))
            # Check for BDD scenario start
            is_scenario_start = line.lower().startswith("scenario:") or line.lower().startswith("given ")

            if (is_item_start or is_scenario_start) and current_block:
                block_text = " ".join(current_block).strip()
                # Clean up initial bullet
                cleaned = re.sub(r"^(\d+[\.\)]|[\*\-\#])\s+", "", block_text).strip()
                is_bdd = bool(cls.BDD_PATTERN.search(cleaned))
                criteria.append(AcceptanceCriterion(
                    id=f"AC-{criterion_idx}",
                    text=cleaned,
                    is_bdd=is_bdd
                ))
                criterion_idx += 1
                current_block = [line]
            else:
                current_block.append(line)

        if current_block:
            block_text = " ".join(current_block).strip()
            cleaned = re.sub(r"^(\d+[\.\)]|[\*\-\#])\s+", "", block_text).strip()
            if cleaned and not cleaned.lower().startswith("acceptance criteria"):
                is_bdd = bool(cls.BDD_PATTERN.search(cleaned))
                criteria.append(AcceptanceCriterion(
                    id=f"AC-{criterion_idx}",
                    text=cleaned,
                    is_bdd=is_bdd
                ))

        # Fallback: if no criteria parsed and text is substantial, create general AC
        if not criteria and raw_text.strip():
            criteria.append(AcceptanceCriterion(
                id="AC-1",
                text=raw_text.strip().splitlines()[0],
                is_bdd=bool(cls.BDD_PATTERN.search(raw_text))
            ))

        return criteria

    @classmethod
    def from_jira_issue_dict(cls, data: dict[str, Any]) -> JiraStoryContext:
        """Construct a JiraStoryContext from Jira REST API issue JSON response."""
        key = data.get("key", "")
        issue_id = str(data.get("id", ""))
        fields = data.get("fields", {})

        summary = fields.get("summary", "")
        raw_desc = fields.get("description", "")
        description = cls.extract_text_from_jira_description(raw_desc)

        status_obj = fields.get("status") or {}
        status = status_obj.get("name", "Unknown") if isinstance(status_obj, dict) else str(status_obj)

        components = [c.get("name") for c in fields.get("components", []) if isinstance(c, dict) and "name" in c]
        labels = fields.get("labels", [])

        # Check for custom fields that might contain Acceptance Criteria explicitly
        custom_ac_text = ""
        for k, v in fields.items():
            if k.startswith("customfield_") and isinstance(v, (str, dict)):
                text_val = cls.extract_text_from_jira_description(v)
                if "given" in text_val.lower() or "acceptance" in text_val.lower() or len(text_val) > 20:
                    # Potential AC custom field
                    custom_ac_text += f"\n{text_val}"

        full_ac_source = description
        if custom_ac_text:
            full_ac_source = f"{description}\n{custom_ac_text}"

        acceptance_criteria = cls.parse_acceptance_criteria(full_ac_source)

        # Detect already linked test cases in issueLinks
        linked_tests: list[str] = []
        issuelinks = fields.get("issuelinks", [])
        for link in issuelinks:
            inward = link.get("inwardIssue")
            outward = link.get("outwardIssue")
            for rel in (inward, outward):
                if rel:
                    rel_type = (rel.get("fields") or {}).get("issuetype", {}).get("name", "")
                    if "test" in rel_type.lower():
                        linked_tests.append(rel.get("key"))

        return JiraStoryContext(
            key=key,
            id=issue_id,
            summary=summary,
            description=description,
            status=status,
            components=components,
            labels=labels,
            acceptance_criteria=acceptance_criteria,
            linked_tests=list(set(linked_tests))
        )
