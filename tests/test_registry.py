"""Tests for the scenario registry."""

from __future__ import annotations

from pathlib import Path

from contractops.models import Scenario
from contractops.registry import ScenarioRegistry


def _make_scenario(sid: str = "test-1", tags: list[str] | None = None) -> Scenario:
    return Scenario(
        id=sid,
        description=f"Test scenario {sid}",
        input=f"Input for {sid}",
        expected={"must_include": ["help"]},
        tags=tags or ["support"],
        metadata={"domain": "support"},
    )


class TestScenarioRegistry:
    def test_register_and_get(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        scenario = _make_scenario("test-register")
        entry = reg.register(scenario, author="tester")

        assert entry["id"] == "test-register"
        assert entry["version"] == 1
        assert entry["author"] == "tester"

        loaded = reg.get("test-register")
        assert loaded is not None
        assert loaded.id == "test-register"

    def test_version_increments_on_change(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        s1 = _make_scenario("versioned")
        reg.register(s1)

        s2 = Scenario(
            id="versioned",
            description="Updated description",
            input="Updated input",
            expected={"must_include": ["updated"]},
        )
        entry = reg.register(s2)
        assert entry["version"] == 2

    def test_no_version_bump_if_unchanged(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        s = _make_scenario("stable")
        reg.register(s)
        entry = reg.register(s)
        assert entry["version"] == 1

    def test_list_all(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        for i in range(5):
            reg.register(_make_scenario(f"list-{i}"))
        assert len(reg.list_all()) == 5

    def test_list_by_tags(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        reg.register(_make_scenario("sec-1", tags=["security"]))
        reg.register(_make_scenario("sup-1", tags=["support"]))
        reg.register(_make_scenario("sec-2", tags=["security"]))

        sec_results = reg.list_all(tags=["security"])
        assert len(sec_results) == 2

    def test_search(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        reg.register(Scenario(
            id="refund-test", description="Handle refund",
            input="Refund me", expected={"must_include": ["refund"]},
            tags=["refund"],
        ))
        reg.register(Scenario(
            id="security-test", description="Security check",
            input="Check security", expected={"must_include": ["security"]},
            tags=["security"],
        ))

        results = reg.search("refund")
        assert len(results) == 1
        assert results[0]["id"] == "refund-test"

    def test_remove(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        reg.register(_make_scenario("to-remove"))
        assert reg.count == 1
        assert reg.remove("to-remove")
        assert reg.count == 0
        assert reg.get("to-remove") is None

    def test_remove_nonexistent(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        assert not reg.remove("nonexistent")

    def test_export_and_import(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        for i in range(3):
            reg.register(_make_scenario(f"export-{i}"))

        export_dir = str(tmp_dir / "exported")
        count = reg.export_pack(export_dir)
        assert count == 3

        reg2 = ScenarioRegistry(str(tmp_dir / "registry2"))
        imported = reg2.import_directory(export_dir, author="importer")
        assert imported == 3
        assert reg2.count == 3

    def test_count(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        assert reg.count == 0
        reg.register(_make_scenario("c1"))
        assert reg.count == 1
        reg.register(_make_scenario("c2"))
        assert reg.count == 2

    def test_get_entry(self, tmp_dir: Path) -> None:
        reg = ScenarioRegistry(str(tmp_dir / "registry"))
        reg.register(_make_scenario("entry-test"), source="unit-test")
        entry = reg.get_entry("entry-test")
        assert entry is not None
        assert entry["source"] == "unit-test"
        assert entry["content_hash"]

    def test_persistence_across_instances(self, tmp_dir: Path) -> None:
        path = str(tmp_dir / "persistent")
        reg1 = ScenarioRegistry(path)
        reg1.register(_make_scenario("persist-test"))
        assert reg1.count == 1

        reg2 = ScenarioRegistry(path)
        assert reg2.count == 1
        assert reg2.get("persist-test") is not None
