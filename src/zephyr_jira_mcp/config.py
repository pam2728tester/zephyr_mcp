"""Configuration and environment management for Jira & Zephyr Squad MCP."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load .env if present
load_dotenv()


class Settings(BaseModel):
    """Runtime configuration for Jira & Zephyr Squad ZAPI integration."""

    jira_base_url: str = Field(
        default_factory=lambda: os.getenv("JIRA_BASE_URL", "https://jira.example.com").rstrip("/")
    )
    jira_pat: Optional[str] = Field(
        default_factory=lambda: os.getenv("JIRA_PAT") or None
    )
    jira_username: Optional[str] = Field(
        default_factory=lambda: os.getenv("JIRA_USERNAME") or None
    )
    jira_password: Optional[str] = Field(
        default_factory=lambda: os.getenv("JIRA_PASSWORD") or None
    )

    jira_test_issue_type: str = Field(
        default_factory=lambda: os.getenv("JIRA_TEST_ISSUE_TYPE", "Test")
    )
    jira_test_link_type: str = Field(
        default_factory=lambda: os.getenv("JIRA_TEST_LINK_TYPE", "Tests")
    )
    default_project_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("JIRA_DEFAULT_PROJECT_KEY") or None
    )

    zapi_base_path: str = Field(
        default_factory=lambda: os.getenv("ZEPHYR_ZAPI_BASE_PATH", "/rest/zapi/latest")
    )
    request_timeout: float = Field(
        default_factory=lambda: float(os.getenv("ZEPHYR_REQUEST_TIMEOUT", "30.0"))
    )
    max_retries: int = Field(
        default_factory=lambda: int(os.getenv("ZEPHYR_MAX_RETRIES", "3"))
    )

    storage_dir: Path = Field(
        default_factory=lambda: Path(
            os.path.expanduser(os.getenv("STORAGE_DIR", "~/.zephyr_jira_mcp"))
        )
    )

    def get_auth_headers(self) -> dict[str, str]:
        """Compute authorization headers based on PAT or Basic Auth."""
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.jira_pat:
            headers["Authorization"] = f"Bearer {self.jira_pat}"
        return headers

    def get_basic_auth(self) -> Optional[tuple[str, str]]:
        """Return (username, password) tuple if PAT is not configured."""
        if not self.jira_pat and self.jira_username and self.jira_password:
            return (self.jira_username, self.jira_password)
        return None


settings = Settings()
