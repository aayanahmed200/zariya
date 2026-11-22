"""Server-side Supabase workspace persistence for Zariya.

This adapter uses the official supabase-py client. The publishable key is
intended for browser-facing, RLS-protected clients; it is deliberately not
used for this server-managed workspace table. Zariya's Flask session identity
is not a Supabase Auth JWT, so privileged reads/upserts require a server-only
Supabase secret key (or the legacy service_role JWT) kept in Vercel env vars.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from supabase import create_client


class SupabaseWorkspaceStore:
    def __init__(self, url: str, secret_key: str) -> None:
        self.url = (url or "").strip().rstrip("/")
        self.secret_key = (secret_key or "").strip()
        self._client: Any | None = None

    @property
    def configured(self) -> bool:
        valid_url = self.url.startswith("https://")
        is_new_secret = bool(
            re.fullmatch(r"sb_secret_[A-Za-z0-9_-]{16,}", self.secret_key)
        )
        is_legacy_service_role = bool(
            self.secret_key.startswith("eyJ")
            and self.secret_key.count(".") == 2
            and len(self.secret_key) >= 40
        )
        return valid_url and (is_new_secret or is_legacy_service_role)

    def _get_client(self) -> Any:
        if not self.configured:
            raise RuntimeError(
                "Supabase cloud storage needs SUPABASE_URL and a server-only "
                "SUPABASE_SECRET_KEY. A publishable key alone cannot write "
                "to Zariya's private workspace table."
            )
        if self._client is None:
            # The SDK client is created only inside the Flask server process.
            # Supabase secret keys have the elevated server role; never send
            # this value to the browser or place it in a NEXT_PUBLIC_ variable.
            self._client = create_client(self.url, self.secret_key)
        return self._client

    @staticmethod
    def _validate_owner_id(owner_id: str) -> None:
        if not isinstance(owner_id, str) or not re.fullmatch(r"[a-f0-9]{64}", owner_id):
            raise ValueError("Invalid workspace owner key.")

    def get_state(self, owner_id: str) -> dict[str, Any] | None:
        self._validate_owner_id(owner_id)
        response = (
            self._get_client()
            .table("zariya_workspaces")
            .select("state")
            .eq("owner_id", owner_id)
            .limit(1)
            .execute()
        )
        rows = getattr(response, "data", None)
        if not isinstance(rows, list) or not rows:
            return None
        state = rows[0].get("state") if isinstance(rows[0], dict) else None
        return state if isinstance(state, dict) else None

    def save_state(self, owner_id: str, state: dict[str, Any]) -> None:
        self._validate_owner_id(owner_id)
        if not isinstance(state, dict):
            raise ValueError("Workspace state must be an object.")
        (
            self._get_client()
            .table("zariya_workspaces")
            .upsert(
                {
                    "owner_id": owner_id,
                    "state": state,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="owner_id",
            )
            .execute()
        )
