"""GitHub integration: post PR comments, set commit statuses, create check runs."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from contractops.models import SuiteResult

logger = logging.getLogger("contractops.github")


def post_pr_comment(
    suite: SuiteResult,
    comment_body: str,
    repo: str | None = None,
    pr_number: int | str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    """Post or update a ContractOps comment on a GitHub PR.

    Requires GITHUB_TOKEN env var or explicit token.
    Reads GITHUB_REPOSITORY and PR number from CI env if not provided.
    """
    token = token or os.getenv("GITHUB_TOKEN")
    if not token:
        logger.warning("GITHUB_TOKEN not set; skipping PR comment.")
        return None

    repo = repo or os.getenv("GITHUB_REPOSITORY", "")
    if not repo:
        logger.warning("GITHUB_REPOSITORY not set; skipping PR comment.")
        return None

    if pr_number is None:
        pr_number = _detect_pr_number()
    if not pr_number:
        logger.warning("Could not detect PR number; skipping PR comment.")
        return None

    existing = _find_existing_comment(repo, int(pr_number), token)

    if existing:
        return _update_comment(repo, existing["id"], comment_body, token)
    return _create_comment(repo, int(pr_number), comment_body, token)


def set_commit_status(
    state: str,
    description: str,
    context: str = "contractops",
    target_url: str = "",
    repo: str | None = None,
    sha: str | None = None,
    token: str | None = None,
) -> dict[str, Any] | None:
    """Set a commit status on the current SHA."""
    token = token or os.getenv("GITHUB_TOKEN")
    repo = repo or os.getenv("GITHUB_REPOSITORY", "")
    sha = sha or os.getenv("GITHUB_SHA", "")

    if not all([token, repo, sha]):
        logger.warning("Missing GitHub env vars; skipping commit status.")
        return None

    payload: dict[str, str] = {
        "state": state,
        "description": description[:140],
        "context": context,
    }
    if target_url:
        payload["target_url"] = target_url

    return _github_api(
        method="POST",
        url=f"https://api.github.com/repos/{repo}/statuses/{sha}",
        body=payload,
        token=token,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_COMMENT_MARKER = "<!-- contractops-report -->"


def _detect_pr_number() -> int | None:
    ref = os.getenv("GITHUB_REF", "")
    if ref.startswith("refs/pull/"):
        parts = ref.split("/")
        if len(parts) >= 3 and parts[2].isdigit():
            return int(parts[2])

    event_path = os.getenv("GITHUB_EVENT_PATH")
    if event_path:
        try:
            with open(event_path, encoding="utf-8") as f:
                event = json.load(f)
            pr_data = event.get("pull_request", {})
            if pr_data.get("number"):
                return int(pr_data["number"])
        except (OSError, json.JSONDecodeError, KeyError):
            pass
    return None


def _find_existing_comment(repo: str, pr_number: int, token: str) -> dict[str, Any] | None:
    try:
        comments = _github_api(
            method="GET",
            url=f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments?per_page=100",
            token=token,
        )
        if isinstance(comments, list):
            for comment in comments:
                if _COMMENT_MARKER in comment.get("body", ""):
                    return comment
    except RuntimeError:
        pass
    return None


def _create_comment(
    repo: str, pr_number: int, body: str, token: str
) -> dict[str, Any]:
    return _github_api(
        method="POST",
        url=f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments",
        body={"body": f"{_COMMENT_MARKER}\n{body}"},
        token=token,
    )


def _update_comment(
    repo: str, comment_id: int, body: str, token: str
) -> dict[str, Any]:
    return _github_api(
        method="PATCH",
        url=f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}",
        body={"body": f"{_COMMENT_MARKER}\n{body}"},
        token=token,
    )


def _github_api(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    token: str = "",
) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = json.dumps(body).encode("utf-8") if body else None
    if method == "GET":
        data = None
    if data is None:
        headers.pop("Content-Type", None)
    else:
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url=url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"GitHub API error: {exc.code} {err_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc
