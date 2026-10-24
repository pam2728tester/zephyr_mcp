"""Zephyr Squad ZAPI client for Jira Server & Data Center."""

import asyncio
import logging
from typing import Any, Optional
import httpx
from .config import Settings, settings
from .models import TestStepSpec

logger = logging.getLogger(__name__)


class ZephyrError(Exception):
    """Base exception for Zephyr ZAPI operations."""
    pass


class ZephyrAuthenticationError(ZephyrError):
    """Authentication failure against Zephyr ZAPI."""
    pass


class ZephyrClient:
    """Manages Zephyr Squad test steps and execution cycles via ZAPI."""

    def __init__(self, config: Optional[Settings] = None):
        self.cfg = config or settings
        self.base_url = self.cfg.jira_base_url.rstrip("/")
        self.zapi_base = self.cfg.zapi_base_path.rstrip("/")

    def _get_client(self) -> httpx.AsyncClient:
        headers = self.cfg.get_auth_headers()
        auth = self.cfg.get_basic_auth()
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            auth=auth,
            timeout=self.cfg.request_timeout,
        )

    async def get_test_steps(self, issue_id: str) -> list[dict[str, Any]]:
        """Retrieve existing test steps for a Zephyr Test issue."""
        url = f"{self.zapi_base}/teststep/{issue_id}"
        async with self._get_client() as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            if resp.status_code == 401 or resp.status_code == 403:
                raise ZephyrAuthenticationError(f"ZAPI Auth failed: {resp.text}")
            if resp.status_code >= 400:
                raise ZephyrError(f"ZAPI get_test_steps failed ({resp.status_code}): {resp.text}")
            data = resp.json()
            if isinstance(data, list):
                return data
            # Some ZAPI versions return {"stepBeanCollection": [...]}
            return data.get("stepBeanCollection", data.get("steps", []))

    async def add_test_step(
        self,
        issue_id: str,
        step: str,
        data: str = "",
        result: str = "",
    ) -> dict[str, Any]:
        """Add a single test step to a Zephyr Test issue with retry logic."""
        url = f"{self.zapi_base}/teststep/{issue_id}"
        payload = {
            "step": step,
            "data": data,
            "result": result,
        }

        last_error: Optional[Exception] = None
        for attempt in range(1, self.cfg.max_retries + 1):
            try:
                async with self._get_client() as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code in (200, 201):
                        return resp.json() if resp.text else {"status": "created"}
                    if resp.status_code in (401, 403):
                        raise ZephyrAuthenticationError(f"ZAPI Auth failed: {resp.text}")
                    if resp.status_code in (429, 502, 503, 504):
                        # Transient error: backoff and retry
                        backoff = 0.5 * (2 ** (attempt - 1))
                        logger.warning(
                            "ZAPI transient error %d on attempt %d. Retrying in %.1fs...",
                            resp.status_code,
                            attempt,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    raise ZephyrError(f"ZAPI add_test_step failed ({resp.status_code}): {resp.text}")
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_error = exc
                backoff = 0.5 * (2 ** (attempt - 1))
                logger.warning("Network error on attempt %d: %s. Retrying in %.1fs...", attempt, exc, backoff)
                await asyncio.sleep(backoff)

        raise ZephyrError(f"Failed to add test step after {self.cfg.max_retries} attempts: {last_error}")

    async def add_test_steps_batch(
        self,
        issue_id: str,
        steps: list[TestStepSpec],
    ) -> list[dict[str, Any]]:
        """Sequentially add all steps to the Zephyr Test issue."""
        created_steps = []
        for s in steps:
            res = await self.add_test_step(
                issue_id=issue_id,
                step=s.step,
                data=s.data,
                result=s.result,
            )
            created_steps.append(res)
        return created_steps
