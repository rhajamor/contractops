"""Tests for policy packs: loading, running, and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from contractops.executors import MockExecutor
from contractops.policy_packs import get_pack, list_packs, load_pack_scenarios
from contractops.suite import run_suite


class TestListPacks:
    def test_returns_all_packs(self) -> None:
        packs = list_packs()
        assert "owasp" in packs
        assert "pii-gdpr" in packs
        assert "hipaa" in packs
        assert "financial" in packs
        assert "enterprise-safety" in packs

    def test_packs_are_sorted(self) -> None:
        packs = list_packs()
        assert packs == sorted(packs)


class TestGetPack:
    def test_returns_scenarios(self) -> None:
        for pack_name in list_packs():
            scenarios = get_pack(pack_name)
            assert len(scenarios) > 0, f"Pack {pack_name} is empty"

    def test_each_scenario_has_required_fields(self) -> None:
        for pack_name in list_packs():
            for raw in get_pack(pack_name):
                assert "id" in raw, f"Missing 'id' in {pack_name}"
                assert "description" in raw, f"Missing 'description' in {pack_name}"
                assert "input" in raw, f"Missing 'input' in {pack_name}"
                assert "expected" in raw, f"Missing 'expected' in {pack_name}"

    def test_unknown_pack_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown policy pack"):
            get_pack("nonexistent-pack")

    def test_owasp_has_security_scenarios(self) -> None:
        scenarios = get_pack("owasp")
        assert len(scenarios) >= 4
        ids = [s["id"] for s in scenarios]
        assert "owasp-prompt-injection" in ids
        assert "owasp-data-exfiltration" in ids

    def test_hipaa_has_healthcare_scenarios(self) -> None:
        scenarios = get_pack("hipaa")
        ids = [s["id"] for s in scenarios]
        assert "hipaa-phi-protection" in ids
        assert "hipaa-no-diagnosis" in ids


class TestLoadPackScenarios:
    def test_returns_scenario_objects(self) -> None:
        scenarios = load_pack_scenarios("owasp")
        assert len(scenarios) > 0
        for s in scenarios:
            assert s.id
            assert s.input
            assert s.expected

    def test_scenarios_have_tags(self) -> None:
        for pack_name in list_packs():
            scenarios = load_pack_scenarios(pack_name)
            for s in scenarios:
                assert len(s.tags) > 0, f"Scenario {s.id} in {pack_name} has no tags"


class TestRunPacks:
    """Run policy packs against mock executors to verify they work end-to-end."""

    def test_owasp_against_mock_v1(self) -> None:
        scenarios = load_pack_scenarios("owasp")
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
        assert result.total == len(scenarios)
        assert result.total > 0

    def test_pii_gdpr_against_mock_v1(self) -> None:
        scenarios = load_pack_scenarios("pii-gdpr")
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
        assert result.total == len(scenarios)

    def test_hipaa_against_mock_v1(self) -> None:
        scenarios = load_pack_scenarios("hipaa")
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
        assert result.total == len(scenarios)

    def test_financial_against_mock_v1(self) -> None:
        scenarios = load_pack_scenarios("financial")
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
        assert result.total == len(scenarios)

    def test_enterprise_safety_against_mock_v1(self) -> None:
        scenarios = load_pack_scenarios("enterprise-safety")
        executor = MockExecutor("v1")
        result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
        assert result.total == len(scenarios)

    def test_all_packs_run_without_error(self) -> None:
        executor = MockExecutor("v1")
        for pack_name in list_packs():
            scenarios = load_pack_scenarios(pack_name)
            result = run_suite(scenarios, executor, min_score=0, min_similarity=0.0)
            assert result.total > 0, f"Pack {pack_name} produced no results"


class TestPacksExport:
    def test_export_creates_files(self, tmp_dir: Path) -> None:
        from contractops.policy_packs import get_pack

        pack_data = get_pack("owasp")
        output_dir = tmp_dir / "exported" / "owasp"
        output_dir.mkdir(parents=True, exist_ok=True)

        for raw in pack_data:
            filepath = output_dir / f"{raw['id']}.json"
            filepath.write_text(json.dumps(raw, indent=2), encoding="utf-8")

        exported_files = list(output_dir.glob("*.json"))
        assert len(exported_files) == len(pack_data)

        for filepath in exported_files:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            assert "id" in data
            assert "expected" in data
