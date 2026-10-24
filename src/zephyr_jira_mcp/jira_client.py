"""Asynchronous Jira REST API client for Jira Server & Data Center."""

import logging
from typing import Any, Optional
import httpx
from .config import Settings, settings

logger = logging.getLogger(__name__)


class JiraError(Exception):
    """Base exception for Jira client operations."""
    pass


class JiraAuthenticationError(JiraError):
    """Authentication or token rejection from Jira."""
    pass


class JiraNotFoundError(JiraError):
    """Requested Jira issue or resource not found."""
    pass


class JiraClient:
    """Handles communication with Jira Server/Data Center REST API v2."""

    def __init__(self, config: Optional[Settings] = None):
        self.cfg = config or settings
        self.base_url = self.cfg.jira_base_url.rstrip("/")

    def _get_client(self) -> httpx.AsyncClient:
        headers = self.cfg.get_auth_headers()
        auth = self.cfg.get_basic_auth()
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            auth=auth,
            timeout=self.cfg.request_timeout,
        )

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Fetch issue details including description, fields, and links."""
        url = f"/rest/api/2/issue/{issue_key}"
        async with self._get_client() as client:
            resp = await client.get(url)
            if resp.status_code == 401 or resp.status_code == 403:
                raise JiraAuthenticationError(f"Authentication failed for Jira ({resp.status_code}): {resp.text}")
            if resp.status_code == 404:
                raise JiraNotFoundError(f"Jira issue '{issue_key}' not found.")
            if resp.status_code >= 400:
                raise JiraError(f"Jira API error ({resp.status_code}): {resp.text}")
            return resp.json()

    async def search_issues(self, jql: str, max_results: int = 50) -> list[dict[str, Any]]:
        """Search Jira issues using JQL."""
        url = "/rest/api/2/search"
        params = {"jql": jql, "maxResults": max_results}
        async with self._get_client() as client:
            resp = await client.get(url, params=params)
            if resp.status_code >= 400:
                raise JiraError(f"JQL search failed ({resp.status_code}): {resp.text}")
            data = resp.json()
            return data.get("issues", [])

    async def create_test_issue(
        self,
        project_key: str,
        summary: str,
        description: str,
        priority: str = "Medium",
        labels: Optional[list[str]] = None,
        components: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Create a new Jira issue of type 'Test'."""
        url = "/rest/api/2/issue"
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": self.cfg.jira_test_issue_type},
                "priority": {"name": priority},
            }
        }
        if labels:
            payload["fields"]["labels"] = labels
        if components:
            payload["fields"]["components"] = [{"name": c} for c in components]

        async with self._get_client() as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 401 or resp.status_code == 403:
                raise JiraAuthenticationError(f"Unauthorized to create issue: {resp.text}")
            if resp.status_code >= 400:
                raise JiraError(f"Failed to create test issue ({resp.status_code}): {resp.text}")
            return resp.json()

    async def link_issue_to_story(
        self,
        story_key: str,
        test_key: str,
        link_type_name: Optional[str] = None,
    ) -> bool:
        """Create bidirectional link between the created Test and parent Story."""
        url = "/rest/api/2/issueLink"
        link_type = link_type_name or self.cfg.jira_test_link_type
        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": story_key},
            "outwardIssue": {"key": test_key},
            "comment": {
                "body": f"Automated traceability link established by Zephyr Jira MCP Server."
            },
        }

        async with self._get_client() as client:
            resp = await client.post(url, json=payload)
            if resp.status_code in (200, 201, 204):
                return True
            # Gracefully handle link types that might have alternate casing or relation
            logger.warning(
                "Link attempt returned %d: %s. Retrying with 'Relates' fallback.",
                resp.status_code,
                resp.text,
            )
            if link_type != "Relates":
                payload["type"]["name"] = "Relates"
                retry_resp = await client.post(url, json=payload)
                if retry_resp.status_code in (200, 201, 204):
                    return True
            raise JiraError(f"Failed to link issues {story_key} <-> {test_key} ({resp.status_code}): {resp.text}")
