"""Tests for notification hooks (using in-memory/mock targets)."""

from __future__ import annotations

from typing import Any

from contractops.models import ScenarioReport, SuiteResult
from contractops.notifications import (
    GenericWebhook,
    NotificationHook,
    NotificationManager,
    SlackWebhook,
    TeamsWebhook,
)


def _make_suite(passed: bool = True) -> SuiteResult:
    scenarios = [
        ScenarioReport(
            scenario_id="test-1",
            passed=passed,
            score=90 if passed else 45,
            contract_pass_rate=1.0 if passed else 0.5,
            similarity=0.95,
            latency_ms=100,
            executor="mock-v1",
            reasons=[] if passed else ["Contract failed"],
            checks=[{"name": "must_include:help", "passed": passed, "detail": "test"}],
            candidate_output="test output",
            diff_preview=[],
            diff_truncated=False,
            tool_calls=[],
        )
    ]
    return SuiteResult(
        passed=passed,
        total=1,
        passed_count=1 if passed else 0,
        failed_count=0 if passed else 1,
        score=90.0 if passed else 45.0,
        scenarios=scenarios,
    )


class InMemoryHook(NotificationHook):
    """Test hook that captures notifications in memory."""

    def __init__(self, name: str = "test", notify_on_pass: bool = False) -> None:
        self.name = name
        self.notify_on_pass = notify_on_pass
        self.received: list[dict[str, Any]] = []

    def send_gate_result(
        self, suite: SuiteResult, context: str = ""
    ) -> dict[str, Any]:
        msg = {
            "type": "gate_result",
            "passed": suite.passed,
            "context": context,
        }
        self.received.append(msg)
        return {"sent": True}

    def send_event(
        self, event_type: str, message: str, details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        msg = {"type": event_type, "message": message, "details": details}
        self.received.append(msg)
        return {"sent": True}


class TestNotificationManager:
    def test_notify_on_failure(self) -> None:
        mgr = NotificationManager()
        hook = InMemoryHook()
        mgr.add_hook(hook)

        results = mgr.notify_gate_result(_make_suite(passed=False))
        assert len(results) == 1
        assert results[0]["success"]
        assert len(hook.received) == 1

    def test_skip_notify_on_pass_by_default(self) -> None:
        mgr = NotificationManager()
        hook = InMemoryHook(notify_on_pass=False)
        mgr.add_hook(hook)

        results = mgr.notify_gate_result(_make_suite(passed=True))
        assert len(results) == 0
        assert len(hook.received) == 0

    def test_notify_on_pass_when_enabled(self) -> None:
        mgr = NotificationManager()
        hook = InMemoryHook(notify_on_pass=True)
        mgr.add_hook(hook)

        results = mgr.notify_gate_result(_make_suite(passed=True))
        assert len(results) == 1
        assert len(hook.received) == 1

    def test_multiple_hooks(self) -> None:
        mgr = NotificationManager()
        hook1 = InMemoryHook(name="hook1")
        hook2 = InMemoryHook(name="hook2")
        mgr.add_hook(hook1)
        mgr.add_hook(hook2)

        mgr.notify_gate_result(_make_suite(passed=False))
        assert len(hook1.received) == 1
        assert len(hook2.received) == 1

    def test_notify_event(self) -> None:
        mgr = NotificationManager()
        hook = InMemoryHook()
        mgr.add_hook(hook)

        results = mgr.notify_event(
            "baseline_approval", "Baseline approved for scenario X"
        )
        assert len(results) == 1
        assert hook.received[0]["type"] == "baseline_approval"

    def test_error_handling(self) -> None:
        class ErrorHook(NotificationHook):
            name = "error"

            def send_gate_result(self, suite: SuiteResult, context: str = "") -> dict[str, Any]:
                raise RuntimeError("Hook failed")

            def send_event(self, event_type: str, message: str,
                           details: dict[str, Any] | None = None) -> dict[str, Any]:
                raise RuntimeError("Hook failed")

        mgr = NotificationManager()
        mgr.add_hook(ErrorHook())
        results = mgr.notify_gate_result(_make_suite(passed=False))
        assert len(results) == 1
        assert not results[0]["success"]
        assert "error" in results[0]


class TestSlackWebhook:
    def test_construction(self) -> None:
        hook = SlackWebhook("https://hooks.slack.com/test", channel="#alerts")
        assert hook.name == "slack"
        assert hook.channel == "#alerts"


class TestTeamsWebhook:
    def test_construction(self) -> None:
        hook = TeamsWebhook("https://outlook.webhook.office.com/test")
        assert hook.name == "teams"


class TestGenericWebhook:
    def test_construction(self) -> None:
        hook = GenericWebhook(
            "https://example.com/webhook",
            headers={"X-Custom": "value"},
            name="custom",
        )
        assert hook.name == "custom"
        assert hook.extra_headers["X-Custom"] == "value"
