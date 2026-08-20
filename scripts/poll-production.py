#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ORGANIZATION = "likelion14-team5"
REPOSITORIES = ("backend", "frontend")
DEPLOY_ROOT = Path(os.getenv("DEPLOY_ROOT", "/opt/global-meeting"))
STATE_FILE = DEPLOY_ROOT / ".last-successful-deployment"
DEPLOY_COMMAND = Path("/usr/local/bin/deploy-global-meeting")


def git_remote_head(repository: str) -> str:
    repository_dir = DEPLOY_ROOT / repository
    result = subprocess.run(
        ["git", "-C", str(repository_dir), "ls-remote", "origin", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    line = result.stdout.strip()
    if not line:
        raise RuntimeError(f"main ref not found for {repository}")
    return line.split()[0]


def latest_push_ci_succeeded(repository: str, head_sha: str) -> bool:
    query = urlencode({"branch": "main", "event": "push", "per_page": 20})
    url = f"https://api.github.com/repos/{ORGANIZATION}/{repository}/actions/runs?{query}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "global-meeting-deployer",
            "X-GitHub-Api-Version": "2022-11-28",
            "Cache-Control": "no-cache",
        },
    )

    with urlopen(request, timeout=30) as response:
        payload = json.load(response)

    expected_path = ".github/workflows/ci.yml"
    for run in payload.get("workflow_runs", []):
        if run.get("head_sha") != head_sha or run.get("path") != expected_path:
            continue
        status = run.get("status")
        conclusion = run.get("conclusion")
        print(
            f"{repository} CI for {head_sha[:12]}: "
            f"status={status} conclusion={conclusion}"
        )
        return status == "completed" and conclusion == "success"

    print(f"{repository} CI for {head_sha[:12]} has not started yet")
    return False


def read_last_successful_deployment() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}

    state: dict[str, str] = {}
    for line in STATE_FILE.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in REPOSITORIES and value:
            state[key] = value
    return state


def main() -> int:
    remote_heads = {
        repository: git_remote_head(repository) for repository in REPOSITORIES
    }
    deployed_heads = read_last_successful_deployment()

    if all(deployed_heads.get(name) == sha for name, sha in remote_heads.items()):
        print("No new main commits to deploy")
        return 0

    if not all(
        latest_push_ci_succeeded(repository, remote_heads[repository])
        for repository in REPOSITORIES
    ):
        print("Deployment skipped until both latest main commits pass CI")
        return 0

    subprocess.run([str(DEPLOY_COMMAND)], check=True, timeout=1800)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Production polling failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
