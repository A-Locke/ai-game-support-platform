"""Thin async wrapper over the Chatwoot Application API.

This is the only module that knows Chatwoot's URL shape and auth header. Every
tool in tools.py goes through here, which keeps the API-access token out of
reach of anything upstream (including the LLM).
"""

from __future__ import annotations

from typing import Any

import httpx


class ChatwootAPIError(Exception):
    """Raised when Chatwoot returns an error response. Carries enough detail
    for a tool to turn it into a structured (non-crashing) result."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Chatwoot API error {status_code}: {detail}")


class ChatwootClient:
    def __init__(self, base_url: str, account_id: int, api_access_token: str, timeout: float = 15.0):
        self._account_id = account_id
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"api_access_token": api_access_token},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _account_path(self, suffix: str) -> str:
        return f"/api/v1/accounts/{self._account_id}{suffix}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, self._account_path(path), **kwargs)
        except httpx.RequestError as exc:
            raise ChatwootAPIError(0, f"Could not reach Chatwoot: {exc}") from exc

        if response.status_code >= 400:
            raise ChatwootAPIError(response.status_code, response.text[:500])

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # -- Conversations -----------------------------------------------------

    async def get_conversation(self, conversation_id: int) -> dict:
        return await self._request("GET", f"/conversations/{conversation_id}")

    async def search_conversations(
        self, query: str | None = None, status: str | None = None, page: int = 1
    ) -> dict:
        params: dict[str, Any] = {"page": page}
        if status:
            params["status"] = status
        if query:
            return await self._request("GET", "/conversations/search", params={"q": query, **params})
        return await self._request("GET", "/conversations", params=params)

    async def get_conversation_messages(self, conversation_id: int) -> dict:
        return await self._request("GET", f"/conversations/{conversation_id}/messages")

    async def update_conversation_status(self, conversation_id: int, status: str) -> dict:
        return await self._request(
            "POST", f"/conversations/{conversation_id}/toggle_status", json={"status": status}
        )

    async def get_conversation_labels(self, conversation_id: int) -> list[str]:
        result = await self._request("GET", f"/conversations/{conversation_id}/labels")
        return result.get("payload", [])

    async def add_conversation_labels(self, conversation_id: int, labels: list[str]) -> dict:
        """Add labels without clobbering existing ones.

        Chatwoot's labels endpoint has *replace* semantics -- POSTing a label list sets the
        conversation's full label set, it does not union with what's already there. Found live:
        calling this for "crash" then again for "human-escalated" left only "human-escalated"
        on the conversation, silently dropping "crash". Read-merge-write here is what makes an
        "add" tool actually add. See PROJECT_JOURNAL.md, Milestone 2.
        """
        existing = await self.get_conversation_labels(conversation_id)
        merged = sorted(set(existing) | set(labels))
        return await self._request(
            "POST", f"/conversations/{conversation_id}/labels", json={"labels": merged}
        )

    async def set_conversation_attributes(self, conversation_id: int, attributes: dict) -> dict:
        return await self._request(
            "POST",
            f"/conversations/{conversation_id}/custom_attributes",
            json={"custom_attributes": attributes},
        )

    async def create_private_note(self, conversation_id: int, content: str) -> dict:
        return await self._request(
            "POST",
            f"/conversations/{conversation_id}/messages",
            json={"content": content, "message_type": "outgoing", "private": True},
        )

    # -- Contacts ------------------------------------------------------------

    async def search_contacts(self, query: str) -> dict:
        return await self._request("GET", "/contacts/search", params={"q": query})

    # -- Reporting -------------------------------------------------------------

    async def filter_conversations(self, conditions: list[dict], page: int = 1) -> dict:
        """Query conversations via Chatwoot's custom-filter API.

        `conditions` follows Chatwoot's filter condition shape, e.g.:
        [{"attribute_key": "created_at", "filter_operator": "is_greater_than",
          "values": ["2026-08-01"], "query_operator": "and"},
         {"attribute_key": "labels", "filter_operator": "equal_to", "values": ["bug"]}]
        """
        return await self._request(
            "POST", "/conversations/filter", params={"page": page}, json={"payload": conditions}
        )
