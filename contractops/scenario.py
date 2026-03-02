"""Scenario loading with support for JSON, YAML, directory scanning, and tag filtering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from contractops.models import Scenario

_REQUIRED_FIELDS = ["id", "description", "input", "expected"]
_SCENARIO_EXTENSIONS = {".json", ".yaml", ".yml"}


def load_scenario(path: str | Path) -> Scenario:
    scenario_path = Path(path)
    raw_text = scenario_path.read_text(encoding="utf-8")

    if scenario_path.suffix in (".yaml", ".yml"):
        raw = yaml.safe_load(raw_text)
    else:
        raw = json.loads(raw_text)

    return _parse_scenario(raw, source=str(scenario_path))


def load_scenarios_from_dir(
    directory: str | Path,
    tags: list[str] | None = None,
    recursive: bool = True,
) -> list[Scenario]:
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise FileNotFoundError(f"Scenario directory not found: {dir_path}")

    pattern = "**/*" if recursive else "*"
    scenarios: list[Scenario] = []
    for path in sorted(dir_path.glob(pattern)):
        if path.suffix not in _SCENARIO_EXTENSIONS or not path.is_file():
            continue
        if _is_suite_file(path):
            continue
        try:
            scenario = load_scenario(path)
            if tags and not scenario.matches_tags(tags):
                continue
            scenarios.append(scenario)
        except (ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError):
            continue

    return scenarios


def validate_scenario(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field_name in _REQUIRED_FIELDS:
        if field_name not in raw:
            errors.append(f"Missing required field: {field_name}")
    if "expected" in raw and not isinstance(raw["expected"], dict):
        errors.append("Field 'expected' must be a mapping.")
    if "id" in raw and not str(raw["id"]).strip():
        errors.append("Field 'id' must be a non-empty string.")
    return errors


def _parse_scenario(raw: dict[str, Any], source: str = "") -> Scenario:
    errors = validate_scenario(raw)
    if errors:
        context = f" (source: {source})" if source else ""
        raise ValueError(f"Invalid scenario{context}: {'; '.join(errors)}")

    tags = raw.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    metadata = dict(raw.get("metadata", {}))
    if "domain" in metadata and metadata["domain"] not in tags:
        tags.append(metadata["domain"])

    return Scenario(
        id=str(raw["id"]),
        description=str(raw["description"]),
        input=str(raw["input"]),
        expected=dict(raw["expected"]),
        metadata=metadata,
        tags=tags,
    )


def _is_suite_file(path: Path) -> bool:
    name_lower = path.stem.lower()
    return name_lower in ("suite", "contractops") or name_lower.startswith("suite_")
