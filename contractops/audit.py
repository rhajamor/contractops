"""Audit trail: immutable run logs, gate decisions, and compliance exports.

Provides append-only event logging for every significant ContractOps action
(baseline saves, approvals, gate decisions, expirations) with cryptographic
integrity via hash chaining.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("contractops.audit")


class AuditLog:
    """Append-only, hash-chained audit log for governance compliance."""

    def __init__(self, log_dir: str = ".contractops/audit") -> None:
        self._dir = Path(log_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self._dir / "audit.jsonl"
        self._last_hash = self._read_last_hash()

    def record(
        self,
        event_type: str,
        scenario_id: str = "",
        details: dict[str, Any] | None = None,
        actor: str = "",
    ) -> dict[str, Any]:
        """Append an audit event. Returns the event record."""
        event = {
            "timestamp": _now_iso(),
            "event_type": event_type,
            "scenario_id": scenario_id,
            "actor": actor,
            "details": details or {},
            "prev_hash": self._last_hash,
        }
        event["hash"] = _hash_event(event)
        self._last_hash = event["hash"]

        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        return event

    def record_gate_decision(
        self,
        scenario_id: str,
        passed: bool,
        score: int,
        executor: str,
        reasons: list[str],
        actor: str = "ci",
    ) -> dict[str, Any]:
        return self.record(
            event_type="gate_decision",
            scenario_id=scenario_id,
            details={
                "passed": passed,
                "score": score,
                "executor": executor,
                "reasons": reasons,
            },
            actor=actor,
        )

    def record_baseline_save(
        self, scenario_id: str, executor: str, location: str, actor: str = ""
    ) -> dict[str, Any]:
        return self.record(
            event_type="baseline_save",
            scenario_id=scenario_id,
            details={"executor": executor, "location": location},
            actor=actor,
        )

    def record_approval(
        self, scenario_id: str, version: int, approver: str
    ) -> dict[str, Any]:
        return self.record(
            event_type="baseline_approval",
            scenario_id=scenario_id,
            details={"version": version},
            actor=approver,
        )

    def record_expiration(
        self, scenario_id: str, reason: str, actor: str = ""
    ) -> dict[str, Any]:
        return self.record(
            event_type="baseline_expiration",
            scenario_id=scenario_id,
            details={"reason": reason},
            actor=actor,
        )

    def get_events(
        self,
        event_type: str = "",
        scenario_id: str = "",
        limit: int = 0,
    ) -> list[dict[str, Any]]:
        """Query audit events with optional filters."""
        events = self._read_all()
        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]
        if scenario_id:
            events = [e for e in events if e.get("scenario_id") == scenario_id]
        if limit > 0:
            events = events[-limit:]
        return events

    def verify_integrity(self) -> tuple[bool, list[str]]:
        """Verify the hash chain integrity of the audit log.

        Returns (is_valid, list_of_errors).
        """
        events = self._read_all()
        errors: list[str] = []
        prev_hash = ""

        for i, event in enumerate(events):
            if event.get("prev_hash", "") != prev_hash:
                errors.append(
                    f"Event {i}: prev_hash mismatch "
                    f"(expected '{prev_hash}', got '{event.get('prev_hash')}')"
                )
            expected_hash = _hash_event({k: v for k, v in event.items() if k != "hash"})
            if event.get("hash") != expected_hash:
                errors.append(f"Event {i}: hash mismatch")
            prev_hash = event.get("hash", "")

        return len(errors) == 0, errors

    def export_json(self, output_path: str) -> int:
        """Export the full audit log as a JSON array."""
        events = self._read_all()
        Path(output_path).write_text(
            json.dumps(events, indent=2), encoding="utf-8"
        )
        return len(events)

    def export_csv(self, output_path: str) -> int:
        """Export the audit log as CSV for spreadsheet/compliance tools."""
        events = self._read_all()
        lines = ["timestamp,event_type,scenario_id,actor,passed,score,details_summary"]
        for event in events:
            details = event.get("details", {})
            passed = str(details.get("passed", ""))
            score = str(details.get("score", ""))
            summary = "; ".join(
                f"{k}={v}" for k, v in details.items()
                if k not in ("passed", "score")
            )[:200]
            lines.append(
                f"{event.get('timestamp', '')},"
                f"{event.get('event_type', '')},"
                f"{event.get('scenario_id', '')},"
                f"{event.get('actor', '')},"
                f"{passed},{score},"
                f'"{summary}"'
            )
        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        return len(events)

    @property
    def event_count(self) -> int:
        return len(self._read_all())

    def _read_all(self) -> list[dict[str, Any]]:
        if not self._log_file.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in self._log_file.read_text(encoding="utf-8").strip().split("\n"):
            if line.strip():
                events.append(json.loads(line))
        return events

    def _read_last_hash(self) -> str:
        events = self._read_all()
        if events:
            return events[-1].get("hash", "")
        return ""


def _hash_event(event: dict[str, Any]) -> str:
    content = json.dumps(event, sort_keys=True, default=str)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
