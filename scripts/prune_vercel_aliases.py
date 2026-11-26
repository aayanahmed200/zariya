"""Remove Vercel's automatic deployment aliases for the Zariya project.

Vercel creates <project>-<scope>.vercel.app and <project>-git-<branch>-<scope>.vercel.app
for every deployment and offers no setting to turn that off, so this script deletes
them again whenever it runs. The custom domain is never touched.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.vercel.com"
KEEP_ALIAS = os.environ.get("KEEP_ALIAS", "zariyas.vercel.app")
ALIAS_PATTERN = re.compile(
    os.environ.get("ALIAS_PATTERN", r"^zariya(-git-[a-z0-9._-]+)?-aayanahmed20\.vercel\.app$")
)


def prunable(name: str) -> bool:
    """Whether this hostname is an automatic alias rather than the custom domain."""
    return name != KEEP_ALIAS and bool(ALIAS_PATTERN.match(name))


def call(method: str, path: str, *, token: str, team_id: str, params: dict | None = None):
    query = urllib.parse.urlencode({"teamId": team_id, **(params or {})})
    request = urllib.request.Request(
        f"{API}{path}?{query}",
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else {}


def list_aliases(token: str, team_id: str, project_id: str):
    cursor = None
    while True:
        params = {"projectId": project_id, "limit": 100}
        if cursor:
            params["from"] = cursor
        page = call("GET", "/v4/aliases", token=token, team_id=team_id, params=params)
        yield from page.get("aliases", [])
        cursor = (page.get("pagination") or {}).get("next")
        if not cursor:
            return


def main() -> int:
    token = os.environ.get("VERCEL_TOKEN", "").strip()
    team_id = os.environ.get("VERCEL_TEAM_ID", "").strip()
    project_id = os.environ.get("VERCEL_PROJECT_ID", "").strip()
    missing = [
        name
        for name, value in (
            ("VERCEL_TOKEN", token),
            ("VERCEL_TEAM_ID", team_id),
            ("VERCEL_PROJECT_ID", project_id),
        )
        if not value
    ]
    if missing:
        print(f"::error::missing {', '.join(missing)}", file=sys.stderr)
        return 1

    removed = 0
    try:
        for alias in list_aliases(token, team_id, project_id):
            name = alias.get("alias") or ""
            uid = alias.get("uid") or ""
            if not uid or not prunable(name):
                continue
            try:
                call("DELETE", f"/v2/aliases/{uid}", token=token, team_id=team_id)
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    continue
                if error.code in (401, 403):
                    print(f"::error::Vercel rejected the token (HTTP {error.code}).", file=sys.stderr)
                    return 1
                print(f"::warning::could not delete {name}: HTTP {error.code}")
                continue
            print(f"Deleted {name}")
            removed += 1
    except urllib.error.HTTPError as error:
        print(f"::error::Vercel alias listing failed (HTTP {error.code}).", file=sys.stderr)
        return 1

    print(f"Removed {removed} automatic alias(es); {KEEP_ALIAS} stays reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
