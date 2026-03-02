"""ContractOps CLI: init, baseline, check, run, validate."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from contractops.assertions import evaluate_contracts
from contractops.baseline import (
    baseline_exists,
    compare_outputs,
    load_baseline,
    save_baseline,
)
from contractops.config import Config, load_config
from contractops.executors import build_executor
from contractops.models import SuiteResult
from contractops.report import (
    build_release_report,
    render_github_comment,
    render_junit_xml,
    render_markdown,
    render_suite_markdown,
)
from contractops.scenario import load_scenario, load_scenarios_from_dir, validate_scenario
from contractops.storage import LocalStorage, build_storage
from contractops.suite import run_suite

logger = logging.getLogger("contractops")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="contractops",
        description="CI-grade behavior contracts and release gates for AI agents.",
    )
    parser.add_argument(
        "--config", default="", help="Path to contractops.yaml config file."
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- init ---
    init_cmd = subparsers.add_parser("init", help="Initialize a ContractOps project.")
    init_cmd.add_argument(
        "--dir", default=".", help="Directory to initialize."
    )
    init_cmd.set_defaults(func=cmd_init)

    # --- baseline ---
    baseline_cmd = subparsers.add_parser("baseline", help="Capture a baseline run.")
    baseline_cmd.add_argument("--scenario", required=True, help="Path to scenario JSON/YAML.")
    baseline_cmd.add_argument("--executor", default="", help="Executor to run.")
    baseline_cmd.add_argument("--baseline-dir", default="", help="Baseline storage directory.")
    baseline_cmd.add_argument("--baseline-file", default="", help="Explicit baseline file path.")
    baseline_cmd.set_defaults(func=cmd_baseline)

    # --- check ---
    check_cmd = subparsers.add_parser("check", help="Run contracts and compare to baseline.")
    check_cmd.add_argument("--scenario", required=True, help="Path to scenario JSON/YAML.")
    check_cmd.add_argument("--executor", default="", help="Executor to run.")
    check_cmd.add_argument("--baseline-dir", default="", help="Baseline storage directory.")
    check_cmd.add_argument("--baseline-file", default="", help="Explicit baseline file path.")
    check_cmd.add_argument("--min-similarity", type=float, default=None)
    check_cmd.add_argument("--min-score", type=int, default=None)
    check_cmd.add_argument("--require-baseline", action="store_true")
    check_cmd.add_argument("--env", default="default", help="Threshold profile name.")
    check_cmd.add_argument(
        "--format", choices=["markdown", "json", "junit"], default="",
        help="Output format.",
    )
    check_cmd.set_defaults(func=cmd_check)

    # --- run (batch) ---
    run_cmd = subparsers.add_parser("run", help="Run all scenarios in a directory.")
    run_cmd.add_argument("--scenarios", required=True, help="Directory of scenario files.")
    run_cmd.add_argument("--executor", default="", help="Executor to use.")
    run_cmd.add_argument("--tags", default="", help="Comma-separated tags to filter scenarios.")
    run_cmd.add_argument("--baseline-dir", default="", help="Baseline storage directory.")
    run_cmd.add_argument("--min-similarity", type=float, default=None)
    run_cmd.add_argument("--min-score", type=int, default=None)
    run_cmd.add_argument("--require-baseline", action="store_true")
    run_cmd.add_argument("--parallel", type=int, default=1, help="Parallel execution workers.")
    run_cmd.add_argument("--env", default="default", help="Threshold profile name.")
    run_cmd.add_argument(
        "--format", choices=["markdown", "json", "junit", "github"], default="",
    )
    run_cmd.add_argument("--output", default="", help="Write report to file instead of stdout.")
    run_cmd.set_defaults(func=cmd_run)

    # --- validate ---
    validate_cmd = subparsers.add_parser("validate", help="Validate scenario files.")
    validate_cmd.add_argument("paths", nargs="+", help="Scenario files or directories to validate.")
    validate_cmd.set_defaults(func=cmd_validate)

    return parser


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.dir)
    scenarios_dir = target / "scenarios"
    baselines_dir = target / ".contractops" / "baselines"

    scenarios_dir.mkdir(parents=True, exist_ok=True)
    baselines_dir.mkdir(parents=True, exist_ok=True)

    config_path = target / "contractops.yaml"
    if not config_path.exists():
        config_path.write_text(_INIT_CONFIG_TEMPLATE, encoding="utf-8")
        print(f"Created config: {config_path}")

    example_path = scenarios_dir / "example.yaml"
    if not example_path.exists():
        example_path.write_text(_INIT_SCENARIO_TEMPLATE, encoding="utf-8")
        print(f"Created example scenario: {example_path}")

    print(f"Initialized ContractOps project in {target.resolve()}")
    print("\nNext steps:")
    print("  1. Edit contractops.yaml to configure your project")
    print("  2. Add scenarios to the scenarios/ directory")
    print("  3. Run: contractops baseline --scenario scenarios/example.yaml")
    print("  4. Run: contractops check --scenario scenarios/example.yaml --executor mock-v2")
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    config = _load_merged_config(args)
    executor_name = args.executor or config.baseline_executor
    scenario = load_scenario(args.scenario)
    executor = build_executor(executor_name)
    result = executor.run(scenario)

    storage = _build_storage(args, config)
    location = save_baseline(result, storage=storage)

    print(
        json.dumps(
            {
                "message": "Baseline saved.",
                "scenario_id": scenario.id,
                "executor": result.executor,
                "location": location,
            },
            indent=2,
        )
    )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    config = _load_merged_config(args)
    threshold = config.threshold_for(args.env)

    executor_name = args.executor or config.default_executor
    min_similarity = (
        args.min_similarity if args.min_similarity is not None
        else threshold.min_similarity
    )
    min_score = args.min_score if args.min_score is not None else threshold.min_score
    require_baseline = args.require_baseline or threshold.require_baseline
    output_format = args.format or config.output_format

    scenario = load_scenario(args.scenario)
    executor = build_executor(executor_name)
    result = executor.run(scenario)
    contract_eval = evaluate_contracts(scenario, result)

    storage = _build_storage(args, config)
    baseline_comparison = None

    if baseline_exists(scenario_id=scenario.id, storage=storage):
        payload = load_baseline(scenario_id=scenario.id, storage=storage)
        baseline_output = str(payload["run_result"]["output"])
        baseline_comparison = compare_outputs(baseline_output, result.output)
    elif require_baseline:
        print(
            json.dumps({"passed": False, "error": f"Baseline not found for '{scenario.id}'."}),
        )
        return 1

    report = build_release_report(
        scenario=scenario,
        run_result=result,
        contract_eval=contract_eval,
        baseline_comparison=baseline_comparison,
        min_similarity=min_similarity,
        min_score=min_score,
    )

    _emit_single_report(report, output_format, min_similarity, min_score, baseline_comparison)
    return 0 if report["passed"] else 1


def cmd_run(args: argparse.Namespace) -> int:
    config = _load_merged_config(args)
    threshold = config.threshold_for(args.env)

    executor_name = args.executor or config.default_executor
    min_similarity = (
        args.min_similarity if args.min_similarity is not None
        else threshold.min_similarity
    )
    min_score = args.min_score if args.min_score is not None else threshold.min_score
    require_baseline = args.require_baseline or threshold.require_baseline
    output_format = args.format or config.output_format

    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else None
    scenarios = load_scenarios_from_dir(args.scenarios, tags=tags)

    if not scenarios:
        print(json.dumps({"error": "No scenarios found.", "path": args.scenarios}))
        return 1

    storage = _build_storage(args, config)
    executor = build_executor(executor_name)

    suite_result = run_suite(
        scenarios=scenarios,
        executor=executor,
        storage=storage,
        min_similarity=min_similarity,
        min_score=min_score,
        require_baseline=require_baseline,
        parallel=args.parallel,
    )

    output_text = _render_suite(suite_result, output_format, min_similarity, min_score)

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output_text)

    return 0 if suite_result.passed else 1


def cmd_validate(args: argparse.Namespace) -> int:
    import yaml

    total = 0
    errors_found = 0

    for path_str in args.paths:
        path = Path(path_str)
        files = []
        if path.is_dir():
            files = (
                sorted(path.rglob("*.json"))
                + sorted(path.rglob("*.yaml"))
                + sorted(path.rglob("*.yml"))
            )
        elif path.is_file():
            files = [path]
        else:
            print(f"  SKIP  {path_str} (not found)")
            continue

        for file_path in files:
            total += 1
            try:
                raw_text = file_path.read_text(encoding="utf-8")
                if file_path.suffix in (".yaml", ".yml"):
                    raw = yaml.safe_load(raw_text) or {}
                else:
                    raw = json.loads(raw_text)
                issues = validate_scenario(raw)
                if issues:
                    errors_found += 1
                    print(f"  FAIL  {file_path}")
                    for issue in issues:
                        print(f"         - {issue}")
                else:
                    print(f"  OK    {file_path}")
            except Exception as exc:
                errors_found += 1
                print(f"  ERROR {file_path}: {exc}")

    print(f"\nValidated {total} files: {total - errors_found} OK, {errors_found} errors.")
    return 0 if errors_found == 0 else 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_merged_config(args: argparse.Namespace) -> Config:
    config_path = getattr(args, "config", "") or None
    return load_config(config_path)


def _build_storage(args: argparse.Namespace, config: Config) -> LocalStorage:
    baseline_dir = getattr(args, "baseline_dir", "") or ""
    if baseline_dir:
        return LocalStorage(baseline_dir)
    return build_storage(
        backend=config.storage.backend,
        base_path=config.storage.base_path,
        bucket=config.storage.bucket,
        prefix=config.storage.prefix,
        region=config.storage.region,
    )


def _emit_single_report(
    report: dict[str, Any],
    fmt: str,
    min_similarity: float,
    min_score: int,
    baseline_comparison: Any,
) -> None:
    if fmt == "json":
        print(json.dumps(report, indent=2))
    else:
        if baseline_comparison is None:
            print("No baseline found. Similarity gate skipped for this run.")
            print("Use `contractops baseline` first for full regression checks.\n")
        print(render_markdown(report, min_similarity, min_score))


def _render_suite(
    suite: SuiteResult, fmt: str, min_similarity: float, min_score: int,
) -> str:
    if fmt == "json":
        return json.dumps(_suite_to_dict(suite), indent=2)
    if fmt == "junit":
        return render_junit_xml(suite)
    if fmt == "github":
        return render_github_comment(suite, min_similarity, min_score)
    return render_suite_markdown(suite, min_similarity, min_score)


def _suite_to_dict(suite: SuiteResult) -> dict[str, Any]:
    return {
        "passed": suite.passed,
        "total": suite.total,
        "passed_count": suite.passed_count,
        "failed_count": suite.failed_count,
        "score": suite.score,
        "pass_rate": suite.pass_rate,
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "passed": s.passed,
                "score": s.score,
                "contract_pass_rate": s.contract_pass_rate,
                "similarity": s.similarity,
                "latency_ms": s.latency_ms,
                "executor": s.executor,
                "reasons": s.reasons,
                "checks": s.checks,
            }
            for s in suite.scenarios
        ],
    }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_INIT_CONFIG_TEMPLATE = """\
# ContractOps configuration
# https://github.com/ideation-lab/contractops

scenarios_dir: scenarios
default_executor: mock-v1
baseline_executor: mock-v1

storage:
  backend: local
  base_path: .contractops/baselines

thresholds:
  default:
    min_similarity: 0.85
    min_score: 80
    require_baseline: false
  staging:
    min_similarity: 0.80
    min_score: 75
    require_baseline: true
  production:
    min_similarity: 0.90
    min_score: 85
    require_baseline: true

output_format: markdown
"""

_INIT_SCENARIO_TEMPLATE = """\
id: example-greeting
description: Agent should greet the user politely and offer help.
input: Hello, I need help with my account.
tags:
  - support
  - onboarding
expected:
  must_include:
    - help
  must_not_include:
    - unfortunately
    - cannot
  max_chars: 500
metadata:
  domain: support
  criticality: medium
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
