"""Tests for the audit trail system."""

from __future__ import annotations

from pathlib import Path

from contractops.audit import AuditLog


class TestAuditLog:
    def test_record_event(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        event = log.record("test_event", scenario_id="s1", actor="tester")
        assert event["event_type"] == "test_event"
        assert event["scenario_id"] == "s1"
        assert event["hash"]
        assert event["timestamp"]

    def test_event_count(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record("event_a")
        log.record("event_b")
        log.record("event_c")
        assert log.event_count == 3

    def test_record_gate_decision(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        event = log.record_gate_decision(
            scenario_id="gate-test",
            passed=False,
            score=65,
            executor="mock-v1",
            reasons=["Contract failed"],
        )
        assert event["event_type"] == "gate_decision"
        assert event["details"]["passed"] is False
        assert event["details"]["score"] == 65

    def test_record_baseline_save(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        event = log.record_baseline_save(
            scenario_id="bl-test",
            executor="mock-v1",
            location="/path/to/baseline.json",
        )
        assert event["event_type"] == "baseline_save"
        assert event["details"]["location"] == "/path/to/baseline.json"

    def test_record_approval(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        event = log.record_approval("approve-test", version=2, approver="admin")
        assert event["event_type"] == "baseline_approval"
        assert event["actor"] == "admin"

    def test_record_expiration(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        event = log.record_expiration("expire-test", reason="Model upgrade")
        assert event["event_type"] == "baseline_expiration"
        assert event["details"]["reason"] == "Model upgrade"

    def test_get_events_filter_by_type(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record("type_a", scenario_id="s1")
        log.record("type_b", scenario_id="s2")
        log.record("type_a", scenario_id="s3")

        results = log.get_events(event_type="type_a")
        assert len(results) == 2

    def test_get_events_filter_by_scenario(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record("event", scenario_id="target")
        log.record("event", scenario_id="other")
        log.record("event", scenario_id="target")

        results = log.get_events(scenario_id="target")
        assert len(results) == 2

    def test_get_events_with_limit(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        for i in range(10):
            log.record("event", scenario_id=f"s{i}")

        results = log.get_events(limit=3)
        assert len(results) == 3

    def test_hash_chain_integrity(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record("event_1")
        log.record("event_2")
        log.record("event_3")

        is_valid, errors = log.verify_integrity()
        assert is_valid, f"Integrity errors: {errors}"
        assert len(errors) == 0

    def test_export_json(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record("event_a", scenario_id="s1")
        log.record("event_b", scenario_id="s2")

        output_path = str(tmp_dir / "export.json")
        count = log.export_json(output_path)
        assert count == 2

        import json
        exported = json.loads(Path(output_path).read_text(encoding="utf-8"))
        assert len(exported) == 2

    def test_export_csv(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "audit"))
        log.record_gate_decision("s1", True, 90, "mock-v1", [])
        log.record_gate_decision("s2", False, 45, "mock-v2", ["Contract failed"])

        output_path = str(tmp_dir / "export.csv")
        count = log.export_csv(output_path)
        assert count == 2

        content = Path(output_path).read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        assert len(lines) == 3  # header + 2 data rows

    def test_persistence_across_instances(self, tmp_dir: Path) -> None:
        path = str(tmp_dir / "persist-audit")
        log1 = AuditLog(path)
        log1.record("event_1")
        log1.record("event_2")

        log2 = AuditLog(path)
        assert log2.event_count == 2
        is_valid, _ = log2.verify_integrity()
        assert is_valid

    def test_empty_log(self, tmp_dir: Path) -> None:
        log = AuditLog(str(tmp_dir / "empty-audit"))
        assert log.event_count == 0
        is_valid, errors = log.verify_integrity()
        assert is_valid
        assert len(errors) == 0
