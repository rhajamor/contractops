"""Notification hooks for failed gates and lifecycle events.

Supports Slack webhooks, Microsoft Teams webhooks, Jira issue creation,
and generic HTTP webhooks. Notifications are fire-and-forget with graceful
error handling so they never block the CI pipeline.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from contractops.models import SuiteResult

logger = logging.getLogger("contractops.notifications")


class NotificationManager:
    """Manages multiple notification channels and dispatches events."""

    def __init__(self) -> None:
        self._hooks: list[NotificationHook] = []

    def add_hook(self, hook: NotificationHook) -> None:
        self._hooks.append(hook)

    def notify_gate_result(self, suite: SuiteResult, context: str = "") -> list[dict[str, Any]]:
        """Send notifications for a gate decision result."""
        results: list[dict[str, Any]] = []
        for hook in self._hooks:
            if suite.passed and not hook.notify_on_pass:
                continue
            try:
                result = hook.send_gate_result(suite, context=context)
                results.append({"hook": hook.name, "success": True, **result})
            except Exception as exc:
                logger.warning("Notification hook '%s' failed: %s", hook.name, exc)
                results.append({"hook": hook.name, "success": False, "error": str(exc)})
        return results

    def notify_event(
        self,
        event_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Send a generic event notification."""
        results: list[dict[str, Any]] = []
        for hook in self._hooks:
            try:
                result = hook.send_event(event_type, message, details)
                results.append({"hook": hook.name, "success": True, **result})
            except Exception as exc:
                logger.warning("Notification hook '%s' failed: %s", hook.name, exc)
                results.append({"hook": hook.name, "success": False, "error": str(exc)})
        return results


class NotificationHook:
    """Base class for notification hooks."""

    name: str = "base"
    notify_on_pass: bool = False

    def send_gate_result(
        self, suite: SuiteResult, context: str = ""
    ) -> dict[str, Any]:
        raise NotImplementedError

    def send_event(
        self,
        event_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class SlackWebhook(NotificationHook):
    """Send notifications to Slack via incoming webhook."""

    def __init__(
        self,
        webhook_url: str,
        channel: str = "",
        notify_on_pass: bool = False,
    ) -> None:
        self.name = "slack"
        self.webhook_url = webhook_url
        self.channel = channel
        self.notify_on_pass = notify_on_pass

    def send_gate_result(
        self, suite: SuiteResult, context: str = ""
    ) -> dict[str, Any]:
        status = "PASS" if suite.passed else "FAIL"
        color = "#36a64f" if suite.passed else "#ff0000"

        failed_text = ""
        if suite.failed_scenarios():
            failed_items = [
                f"- `{s.scenario_id}`: {', '.join(s.reasons[:2])}"
                for s in suite.failed_scenarios()[:5]
            ]
            failed_text = "\n".join(failed_items)

        payload = {
            "attachments": [{
                "color": color,
                "title": f"ContractOps Gate: {status}",
                "text": (
                    f"*{suite.passed_count}/{suite.total}* scenarios passed | "
                    f"avg score *{suite.score:.0f}*"
                    f"{f' | {context}' if context else ''}"
                ),
                "fields": [],
            }],
        }

        if failed_text:
            payload["attachments"][0]["fields"].append({
                "title": "Failed Scenarios",
                "value": failed_text,
                "short": False,
            })

        if self.channel:
            payload["channel"] = self.channel

        return _send_webhook(self.webhook_url, payload)

    def send_event(
        self, event_type: str, message: str, details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "text": f"*[ContractOps {event_type}]* {message}",
        }
        if self.channel:
            payload["channel"] = self.channel
        return _send_webhook(self.webhook_url, payload)


class TeamsWebhook(NotificationHook):
    """Send notifications to Microsoft Teams via incoming webhook."""

    def __init__(self, webhook_url: str, notify_on_pass: bool = False) -> None:
        self.name = "teams"
        self.webhook_url = webhook_url
        self.notify_on_pass = notify_on_pass

    def send_gate_result(
        self, suite: SuiteResult, context: str = ""
    ) -> dict[str, Any]:
        status = "PASS" if suite.passed else "FAIL"
        theme_color = "00FF00" if suite.passed else "FF0000"

        facts = [
            {"name": "Status", "value": status},
            {"name": "Passed", "value": f"{suite.passed_count}/{suite.total}"},
            {"name": "Score", "value": f"{suite.score:.0f}"},
        ]
        if context:
            facts.append({"name": "Context", "value": context})

        payload = {
            "@type": "MessageCard",
            "themeColor": theme_color,
            "summary": f"ContractOps Gate: {status}",
            "sections": [{
                "activityTitle": f"ContractOps Gate: {status}",
                "facts": facts,
            }],
        }

        return _send_webhook(self.webhook_url, payload)

    def send_event(
        self, event_type: str, message: str, details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "@type": "MessageCard",
            "summary": f"ContractOps: {event_type}",
            "sections": [{"activityTitle": event_type, "text": message}],
        }
        return _send_webhook(self.webhook_url, payload)


class JiraHook(NotificationHook):
    """Create Jira issues for failed gates."""

    def __init__(
        self,
        base_url: str,
        project_key: str,
        api_token: str,
        email: str,
        issue_type: str = "Bug",
    ) -> None:
        self.name = "jira"
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.api_token = api_token
        self.email = email
        self.issue_type = issue_type
        self.notify_on_pass = False

    def send_gate_result(
        self, suite: SuiteResult, context: str = ""
    ) -> dict[str, Any]:
        if suite.passed:
            return {"skipped": True}

        failed_ids = [s.scenario_id for s in suite.failed_scenarios()[:10]]
        description = (
            f"ContractOps gate failed.\n\n"
            f"Passed: {suite.passed_count}/{suite.total}\n"
            f"Score: {suite.score:.0f}\n\n"
            f"Failed scenarios:\n" +
            "\n".join(f"- {sid}" for sid in failed_ids)
        )
        if context:
            description += f"\n\nContext: {context}"

        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": f"ContractOps gate failure ({suite.failed_count} scenarios)",
                "description": description,
                "issuetype": {"name": self.issue_type},
            }
        }

        import base64
        auth = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return _send_webhook(
            f"{self.base_url}/rest/api/2/issue",
            payload,
            headers={"Authorization": f"Basic {auth}"},
        )

    def send_event(
        self, event_type: str, message: str, details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {"skipped": True, "reason": "Jira only creates issues for gate failures"}


class GenericWebhook(NotificationHook):
    """Send notifications to any HTTP endpoint."""

    def __init__(
        self,
        webhook_url: str,
        headers: dict[str, str] | None = None,
        notify_on_pass: bool = False,
        name: str = "webhook",
    ) -> None:
        self.name = name
        self.webhook_url = webhook_url
        self.extra_headers = headers or {}
        self.notify_on_pass = notify_on_pass

    def send_gate_result(
        self, suite: SuiteResult, context: str = ""
    ) -> dict[str, Any]:
        payload = {
            "event": "gate_result",
            "passed": suite.passed,
            "total": suite.total,
            "passed_count": suite.passed_count,
            "failed_count": suite.failed_count,
            "score": suite.score,
            "context": context,
            "failed_scenarios": [
                {"id": s.scenario_id, "score": s.score, "reasons": s.reasons}
                for s in suite.failed_scenarios()
            ],
        }
        return _send_webhook(self.webhook_url, payload, headers=self.extra_headers)

    def send_event(
        self, event_type: str, message: str, details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "event": event_type,
            "message": message,
            "details": details or {},
        }
        return _send_webhook(self.webhook_url, payload, headers=self.extra_headers)


def _send_webhook(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
    timeout: int = 15,
) -> dict[str, Any]:
    """Fire-and-forget HTTP POST to a webhook URL."""
    data = json.dumps(payload).encode("utf-8")
    all_headers: dict[str, str] = {"Content-Type": "application/json"}
    if headers:
        all_headers.update(headers)

    request = urllib.request.Request(
        url=url, data=data, method="POST", headers=all_headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {"status": response.status, "sent": True}
    except urllib.error.HTTPError as exc:
        logger.warning("Webhook failed (%s): %s", url, exc.code)
        return {"status": exc.code, "sent": False, "error": str(exc)}
    except urllib.error.URLError as exc:
        logger.warning("Webhook unreachable (%s): %s", url, exc.reason)
        return {"sent": False, "error": str(exc.reason)}
