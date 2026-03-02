from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_CONFIG_FILENAMES = ["contractops.yaml", "contractops.yml", "contractops.json"]


@dataclass
class ThresholdProfile:
    min_similarity: float = 0.85
    min_score: int = 80
    require_baseline: bool = False


@dataclass
class StorageConfig:
    backend: str = "local"
    base_path: str = ".contractops/baselines"
    bucket: str = ""
    prefix: str = "contractops/baselines"
    region: str = ""


@dataclass
class Config:
    scenarios_dir: str = "scenarios"
    default_executor: str = "mock-v1"
    baseline_executor: str = "mock-v1"
    storage: StorageConfig = field(default_factory=StorageConfig)
    thresholds: dict[str, ThresholdProfile] = field(default_factory=dict)
    default_tags: list[str] = field(default_factory=list)
    output_format: str = "markdown"

    def threshold_for(self, env: str = "default") -> ThresholdProfile:
        if env in self.thresholds:
            return self.thresholds[env]
        return self.thresholds.get("default", ThresholdProfile())


def find_config(start_dir: str | Path | None = None) -> Path | None:
    search = Path(start_dir) if start_dir else Path.cwd()
    for name in _CONFIG_FILENAMES:
        candidate = search / name
        if candidate.is_file():
            return candidate
    return None


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        found = find_config()
        if found is None:
            return Config()
        path = found

    config_path = Path(path)
    raw_text = config_path.read_text(encoding="utf-8")

    if config_path.suffix == ".json":
        raw = json.loads(raw_text)
    else:
        raw = yaml.safe_load(raw_text) or {}

    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> Config:
    storage_raw = raw.get("storage", {})
    storage = StorageConfig(
        backend=storage_raw.get("backend", "local"),
        base_path=storage_raw.get("base_path", ".contractops/baselines"),
        bucket=storage_raw.get("bucket", ""),
        prefix=storage_raw.get("prefix", "contractops/baselines"),
        region=storage_raw.get("region", ""),
    )

    thresholds: dict[str, ThresholdProfile] = {}
    for env_name, env_raw in raw.get("thresholds", {}).items():
        thresholds[env_name] = ThresholdProfile(
            min_similarity=float(env_raw.get("min_similarity", 0.85)),
            min_score=int(env_raw.get("min_score", 80)),
            require_baseline=bool(env_raw.get("require_baseline", False)),
        )

    return Config(
        scenarios_dir=raw.get("scenarios_dir", "scenarios"),
        default_executor=raw.get("default_executor", "mock-v1"),
        baseline_executor=raw.get("baseline_executor", "mock-v1"),
        storage=storage,
        thresholds=thresholds,
        default_tags=raw.get("default_tags", []),
        output_format=raw.get("output_format", "markdown"),
    )
