"""Small server-only Supabase REST adapter for Zariya workspace state.

The Supabase secret/service-role key never leaves the Flask process. RLS is
enabled on the table and no anon/authenticated policies are granted; these
requests are authenticated only from this server.
"""
from __future__ import annotations

import re
from typing import Any

import requests


class SupabaseWorkspaceStore:
    def __init__(self, url: str, api_key: str, timeout: float = 8.0) -> None:
        self.url = (url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return (
            self.url.startswith("https://")
            and bool(re.fullmatch(r"[A-Za-z0-9_-]+", self.api_key))
            and len(self.api_key) >= 24
        )

    def _headers(self, *, upsert: bool = False) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError("Supabase cloud storage is not configured.")
        headers = {
            "apikey": self.api_key,
            "Accept": "application/json",
        }
        # Legacy service-role keys are JWTs. New sb_secret_* keys are API keys
        # and should be sent as apikey only, not as a forged bearer user token.
        if self.api_key.startswith("eyJ") and self.api_key.count(".") == 2:
            headers["Authorization"] = "Bearer " + self.api_key
        if upsert:
            headers["Content-Type"] = "application/json"
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        return headers

    def _endpoint(self) -> str:
        return self.url + "/rest/v1/zariya_workspaces"

    @staticmethod
    def _validate_owner_id(owner_id: str) -> None:
        if not isinstance(owner_id, str) or not re.fullmatch(r"[a-f0-9]{64}", owner_id):
            raise ValueError("Invalid workspace owner key.")

    def get_state(self, owner_id: str) -> dict[str, Any] | None:
        self._validate_owner_id(owner_id)
        response = requests.get(
            self._endpoint(),
            params={"select": "state", "owner_id": "eq." + owner_id, "limit": "1"},
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            return None
        state = rows[0].get("state") if isinstance(rows[0], dict) else None
        return state if isinstance(state, dict) else None

    def save_state(self, owner_id: str, state: dict[str, Any]) -> None:
        self._validate_owner_id(owner_id)
        if not isinstance(state, dict):
            raise ValueError("Workspace state must be an object.")
        response = requests.post(
            self._endpoint(),
            params={"on_conflict": "owner_id"},
            headers=self._headers(upsert=True),
            json={
                "owner_id": owner_id,
                "state": state,
                "updated_at": "now()",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
