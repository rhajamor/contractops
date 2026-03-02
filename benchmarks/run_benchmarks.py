"""ContractOps Benchmark Runner.

Runs all scenarios against every installed Ollama model, collects pass rates,
latency, token throughput, and contract check details, then emits a rich
comparison report.

Usage:
    python benchmarks/run_benchmarks.py                     # all models, all scenarios
    python benchmarks/run_benchmarks.py --models qwen3:8b   # single model
    python benchmarks/run_benchmarks.py --output results.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contractops.assertions import evaluate_contracts
from contractops.executors import OllamaExecutor
from contractops.models import Scenario
from contractops.scenario import load_scenarios_from_dir

MODELS = [
    "qwen3:8b",
    "gemma3:4b",
    "llama3.1:8b",
    "deepseek-r1:8b",
    "gpt-oss:20b",
    "phi4-mini",
    "mistral:7b",
]


@dataclass
class CheckDetail:
    name: str
    passed: bool
    detail: str


@dataclass
class ScenarioBenchmark:
    scenario_id: str
    model: str
    passed: bool
    pass_rate: float
    latency_ms: int
    output_chars: int
    tokens_generated: int
    tokens_per_second: float
    checks: list[CheckDetail] = field(default_factory=list)
    output_preview: str = ""
    error: str | None = None


@dataclass
class ModelSummary:
    model: str
    total_scenarios: int
    passed: int
    failed: int
    pass_rate: float
    avg_latency_ms: float
    median_latency_ms: float
    avg_tokens_per_second: float
    avg_contract_pass_rate: float


@dataclass
class BenchmarkReport:
    timestamp: str
    scenarios_dir: str
    num_scenarios: int
    models: list[str]
    model_summaries: list[ModelSummary]
    details: list[ScenarioBenchmark]
    total_duration_sec: float


def run_scenario_against_model(
    scenario: Scenario, model: str, base_url: str, num_ctx: int, timeout: int,
) -> ScenarioBenchmark:
    executor = OllamaExecutor(
        model=model, base_url=base_url, num_ctx=num_ctx, timeout=timeout,
    )

    try:
        result = executor.run(scenario)
        evaluation = evaluate_contracts(scenario, result)

        checks = [
            CheckDetail(name=c.name, passed=c.passed, detail=c.detail)
            for c in evaluation.checks
        ]

        tokens_gen = result.extra.get("tokens_generated", 0)
        tps = result.extra.get("tokens_per_second", 0.0)

        preview = result.output[:200] + ("..." if len(result.output) > 200 else "")

        return ScenarioBenchmark(
            scenario_id=scenario.id,
            model=model,
            passed=evaluation.passed,
            pass_rate=evaluation.pass_rate,
            latency_ms=result.latency_ms,
            output_chars=len(result.output),
            tokens_generated=tokens_gen,
            tokens_per_second=tps,
            checks=checks,
            output_preview=preview,
        )

    except Exception as exc:
        return ScenarioBenchmark(
            scenario_id=scenario.id,
            model=model,
            passed=False,
            pass_rate=0.0,
            latency_ms=0,
            output_chars=0,
            tokens_generated=0,
            tokens_per_second=0.0,
            error=str(exc),
        )


def compute_model_summary(model: str, results: list[ScenarioBenchmark]) -> ModelSummary:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    latencies = [r.latency_ms for r in results if r.error is None]
    tps_values = [r.tokens_per_second for r in results if r.tokens_per_second > 0]
    pass_rates = [r.pass_rate for r in results if r.error is None]

    sorted_lat = sorted(latencies) if latencies else [0]
    median_lat = sorted_lat[len(sorted_lat) // 2]

    return ModelSummary(
        model=model,
        total_scenarios=total,
        passed=passed,
        failed=total - passed,
        pass_rate=round(passed / total, 4) if total else 0,
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0,
        median_latency_ms=median_lat,
        avg_tokens_per_second=round(sum(tps_values) / len(tps_values), 2) if tps_values else 0,
        avg_contract_pass_rate=round(sum(pass_rates) / len(pass_rates), 4) if pass_rates else 0,
    )


def print_summary_table(summaries: list[ModelSummary]) -> None:
    try:
        from tabulate import tabulate
    except ImportError:
        for s in summaries:
            print(f"  {s.model}: {s.passed}/{s.total_scenarios} passed, "
                  f"avg {s.avg_latency_ms}ms, {s.avg_tokens_per_second} tok/s")
        return

    headers = [
        "Model", "Pass Rate", "Passed", "Failed",
        "Avg Latency", "Median Latency", "Avg tok/s", "Contract Rate",
    ]
    rows = []
    for s in sorted(summaries, key=lambda x: x.pass_rate, reverse=True):
        rows.append([
            s.model,
            f"{s.pass_rate:.0%}",
            s.passed,
            s.failed,
            f"{s.avg_latency_ms:.0f}ms",
            f"{s.median_latency_ms}ms",
            f"{s.avg_tokens_per_second:.1f}",
            f"{s.avg_contract_pass_rate:.0%}",
        ])

    print(tabulate(rows, headers=headers, tablefmt="github"))


def print_failure_details(details: list[ScenarioBenchmark]) -> None:
    failures = [d for d in details if not d.passed]
    if not failures:
        print("\n  All scenarios passed across all models!")
        return

    print(f"\n  {len(failures)} failure(s):\n")
    for f in failures:
        print(f"  [{f.model}] {f.scenario_id}")
        if f.error:
            print(f"    ERROR: {f.error}")
        else:
            for c in f.checks:
                status = "PASS" if c.passed else "FAIL"
                print(f"    {status} {c.name}: {c.detail}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="ContractOps LLM Benchmark Runner")
    parser.add_argument(
        "--scenarios", default="examples",
        help="Directory containing scenario JSON/YAML files",
    )
    parser.add_argument(
        "--models", nargs="*", default=None,
        help="Specific models to benchmark (default: all installed)",
    )
    parser.add_argument(
        "--base-url", default="http://localhost:11434",
        help="Ollama server URL",
    )
    parser.add_argument("--num-ctx", type=int, default=4096, help="Context window size")
    parser.add_argument("--timeout", type=int, default=120, help="Per-request timeout (sec)")
    parser.add_argument("--output", default="", help="Write JSON results to file")
    parser.add_argument("--runs", type=int, default=1, help="Repeat count per scenario (for variance)")
    args = parser.parse_args()

    scenarios = load_scenarios_from_dir(args.scenarios)
    if not scenarios:
        print(f"ERROR: No scenarios found in {args.scenarios}")
        return 1

    models = args.models or MODELS

    probe = OllamaExecutor(model=models[0], base_url=args.base_url)
    if not probe.is_available():
        print(f"ERROR: Ollama server not reachable at {args.base_url}")
        print("       Start it with: ollama serve")
        return 1

    available = probe.list_models()
    available_short = {m.split(":")[0] for m in available} | set(available)
    missing = [m for m in models if m not in available_short and m not in available]
    if missing:
        print(f"WARNING: Models not found locally: {missing}")
        print(f"         Available: {available}")
        models = [m for m in models if m not in missing]

    print("=" * 72)
    print("  ContractOps LLM Benchmark")
    print("=" * 72)
    print(f"  Scenarios : {len(scenarios)} from {args.scenarios}/")
    print(f"  Models    : {len(models)} ({', '.join(models)})")
    print(f"  Runs      : {args.runs}x per scenario")
    print("=" * 72)

    all_details: list[ScenarioBenchmark] = []
    start_time = time.time()

    for model in models:
        print(f"\n{'-' * 72}")
        print(f"  Model: {model}")
        print(f"{'-' * 72}")

        for run_idx in range(args.runs):
            for scenario in scenarios:
                label = f"  [{run_idx + 1}/{args.runs}] {scenario.id}"
                print(f"{label} ... ", end="", flush=True)

                result = run_scenario_against_model(
                    scenario, model, args.base_url, args.num_ctx, args.timeout,
                )
                all_details.append(result)

                if result.error:
                    print(f"ERROR ({result.error[:60]})")
                elif result.passed:
                    print(f"PASS  ({result.latency_ms}ms, {result.tokens_per_second:.1f} tok/s)")
                else:
                    failed_checks = [c.name for c in result.checks if not c.passed]
                    print(f"FAIL  ({result.latency_ms}ms) [{', '.join(failed_checks)}]")

    total_duration = time.time() - start_time

    model_summaries = []
    for model in models:
        model_results = [d for d in all_details if d.model == model]
        model_summaries.append(compute_model_summary(model, model_results))

    print(f"\n{'=' * 72}")
    print("  RESULTS SUMMARY")
    print(f"{'=' * 72}\n")
    print_summary_table(model_summaries)
    print_failure_details(all_details)

    print(f"\n  Total benchmark time: {total_duration:.1f}s")
    print(f"  Total runs: {len(all_details)}")

    report = BenchmarkReport(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
        scenarios_dir=args.scenarios,
        num_scenarios=len(scenarios),
        models=models,
        model_summaries=model_summaries,
        details=all_details,
        total_duration_sec=round(total_duration, 2),
    )

    if args.output:
        Path(args.output).write_text(
            json.dumps(asdict(report), indent=2, default=str),
            encoding="utf-8",
        )
        print(f"\n  Full results written to: {args.output}")

    any_model_perfect = any(s.pass_rate == 1.0 for s in model_summaries)
    if any_model_perfect:
        print("\n  At least one model achieved 100% pass rate.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
