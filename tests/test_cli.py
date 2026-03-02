import json
from pathlib import Path

from contractops.cli import main
from tests.conftest import CUSTOMER_SCENARIO_PATH, EXAMPLES_DIR


class TestCmdInit:
    def test_creates_project_structure(self, tmp_dir: Path):
        code = main(["init", "--dir", str(tmp_dir)])
        assert code == 0
        assert (tmp_dir / "contractops.yaml").exists()
        assert (tmp_dir / "scenarios").is_dir()
        assert (tmp_dir / "scenarios" / "example.yaml").exists()
        assert (tmp_dir / ".contractops" / "baselines").is_dir()

    def test_idempotent(self, tmp_dir: Path):
        main(["init", "--dir", str(tmp_dir)])
        code = main(["init", "--dir", str(tmp_dir)])
        assert code == 0


class TestCmdBaseline:
    def test_captures_baseline(self, tmp_dir: Path):
        code = main([
            "baseline",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir / "baselines"),
        ])
        assert code == 0
        baselines = list((tmp_dir / "baselines").glob("*.json"))
        assert len(baselines) == 1


class TestCmdCheck:
    def test_passes_with_v1(self, tmp_dir: Path):
        main([
            "baseline",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
        ])
        code = main([
            "check",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
        ])
        assert code == 0

    def test_fails_with_v2(self, tmp_dir: Path):
        main([
            "baseline",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
        ])
        code = main([
            "check",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v2",
            "--baseline-dir", str(tmp_dir),
            "--require-baseline",
        ])
        assert code == 1

    def test_json_format(self, tmp_dir: Path, capsys):
        code = main([
            "check",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
            "--format", "json",
        ])
        assert code == 0
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["passed"] is True

    def test_require_baseline_missing(self, tmp_dir: Path):
        code = main([
            "check",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir / "empty"),
            "--require-baseline",
        ])
        assert code == 1


class TestCmdRun:
    def test_runs_all_examples(self, tmp_dir: Path):
        assert main([
            "run",
            "--scenarios", str(EXAMPLES_DIR),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
            "--format", "json",
        ]) == 0

    def test_json_output(self, tmp_dir: Path, capsys):
        main([
            "run",
            "--scenarios", str(EXAMPLES_DIR),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
            "--format", "json",
        ])
        output = capsys.readouterr().out
        data = json.loads(output)
        assert "total" in data
        assert "scenarios" in data

    def test_junit_output(self, tmp_dir: Path, capsys):
        main([
            "run",
            "--scenarios", str(EXAMPLES_DIR),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
            "--format", "junit",
        ])
        output = capsys.readouterr().out
        assert "<?xml" in output
        assert "testsuites" in output

    def test_write_to_file(self, tmp_dir: Path):
        report_file = tmp_dir / "report.md"
        code = main([
            "run",
            "--scenarios", str(EXAMPLES_DIR),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir / "baselines"),
            "--output", str(report_file),
        ])
        assert code == 0
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        assert "ContractOps" in content

    def test_filter_by_tags(self, scenario_dir: Path, tmp_dir: Path, capsys):
        main([
            "run",
            "--scenarios", str(scenario_dir),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
            "--tags", "refund",
            "--format", "json",
        ])
        output = capsys.readouterr().out
        data = json.loads(output)
        assert data["total"] == 1

    def test_no_scenarios_found(self, tmp_dir: Path):
        empty = tmp_dir / "empty"
        empty.mkdir()
        code = main([
            "run",
            "--scenarios", str(empty),
            "--executor", "mock-v1",
        ])
        assert code == 1


class TestCmdValidate:
    def test_valid_files(self):
        code = main(["validate", str(EXAMPLES_DIR)])
        assert code == 0

    def test_invalid_file(self, tmp_dir: Path):
        bad = tmp_dir / "bad.json"
        bad.write_text(json.dumps({"description": "missing fields"}), encoding="utf-8")
        code = main(["validate", str(bad)])
        assert code == 1

    def test_mixed_valid_invalid(self, tmp_dir: Path):
        good = tmp_dir / "good.json"
        good.write_text(json.dumps({
            "id": "ok", "description": "d", "input": "i", "expected": {},
        }), encoding="utf-8")
        bad = tmp_dir / "bad.json"
        bad.write_text(json.dumps({"id": "x"}), encoding="utf-8")
        code = main(["validate", str(tmp_dir)])
        assert code == 1


class TestEndToEnd:
    def test_full_workflow(self, tmp_dir: Path):
        """baseline -> check pass -> check fail, full lifecycle."""
        bl_code = main([
            "baseline",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
        ])
        assert bl_code == 0

        pass_code = main([
            "check",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v1",
            "--baseline-dir", str(tmp_dir),
            "--require-baseline",
        ])
        assert pass_code == 0

        fail_code = main([
            "check",
            "--scenario", str(CUSTOMER_SCENARIO_PATH),
            "--executor", "mock-v2",
            "--baseline-dir", str(tmp_dir),
            "--require-baseline",
        ])
        assert fail_code == 1
