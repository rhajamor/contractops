import json
from pathlib import Path

import pytest

from contractops.scenario import (
    load_scenario,
    load_scenarios_from_dir,
    validate_scenario,
)
from tests.conftest import CUSTOMER_SCENARIO_PATH


class TestLoadScenario:
    def test_load_json(self):
        scenario = load_scenario(str(CUSTOMER_SCENARIO_PATH))
        assert scenario.id == "customer-refund-enterprise"
        assert "refund" in scenario.input.lower()
        assert "must_include" in scenario.expected

    def test_load_yaml(self, sample_yaml_scenario: Path):
        scenario = load_scenario(sample_yaml_scenario)
        assert scenario.id == "yaml-test"
        assert "support" in scenario.tags

    def test_missing_required_fields(self, tmp_dir: Path):
        bad = {"id": "x", "description": "d"}
        path = tmp_dir / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError, match="Missing required field"):
            load_scenario(path)

    def test_tags_from_metadata_domain(self, tmp_dir: Path):
        data = {
            "id": "x", "description": "d", "input": "i",
            "expected": {}, "metadata": {"domain": "finance"},
        }
        path = tmp_dir / "s.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        scenario = load_scenario(path)
        assert "finance" in scenario.tags


class TestLoadScenariosFromDir:
    def test_loads_all(self, scenario_dir: Path):
        scenarios = load_scenarios_from_dir(scenario_dir)
        assert len(scenarios) == 3

    def test_filter_by_tags(self, scenario_dir: Path):
        scenarios = load_scenarios_from_dir(scenario_dir, tags=["refund"])
        assert len(scenarios) == 1
        assert scenarios[0].id == "scenario-0"

    def test_empty_dir(self, tmp_dir: Path):
        empty = tmp_dir / "empty"
        empty.mkdir()
        scenarios = load_scenarios_from_dir(empty)
        assert scenarios == []

    def test_nonexistent_dir(self, tmp_dir: Path):
        with pytest.raises(FileNotFoundError):
            load_scenarios_from_dir(tmp_dir / "nope")


class TestValidateScenario:
    def test_valid(self):
        raw = {"id": "x", "description": "d", "input": "i", "expected": {}}
        assert validate_scenario(raw) == []

    def test_missing_fields(self):
        raw = {"description": "d"}
        errors = validate_scenario(raw)
        assert any("id" in e for e in errors)
        assert any("input" in e for e in errors)
        assert any("expected" in e for e in errors)

    def test_empty_id(self):
        raw = {"id": " ", "description": "d", "input": "i", "expected": {}}
        errors = validate_scenario(raw)
        assert any("non-empty" in e for e in errors)

    def test_expected_not_dict(self):
        raw = {"id": "x", "description": "d", "input": "i", "expected": "wrong"}
        errors = validate_scenario(raw)
        assert any("mapping" in e for e in errors)
