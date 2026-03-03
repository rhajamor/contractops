"""Scenario registry: versioned, tagged, cross-repo scenario management.

Provides a central index of all scenarios with version tracking, tagging,
search capabilities, and import/export for sharing across repositories.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contractops.models import Scenario
from contractops.scenario import load_scenario

logger = logging.getLogger("contractops.registry")


class ScenarioRegistry:
    """File-backed scenario registry with versioning and metadata."""

    _INDEX_FILE = "_registry_index.json"

    def __init__(self, base_dir: str = ".contractops/registry") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._index = self._load_index()

    def register(
        self,
        scenario: Scenario,
        author: str = "",
        source: str = "",
    ) -> dict[str, Any]:
        """Register or update a scenario in the registry."""
        content_hash = _hash_scenario(scenario)
        existing = self._index.get(scenario.id)

        version = 1
        if existing is not None:
            if existing.get("content_hash") == content_hash:
                return existing
            version = existing.get("version", 0) + 1

        entry: dict[str, Any] = {
            "id": scenario.id,
            "description": scenario.description,
            "tags": scenario.tags,
            "metadata": scenario.metadata,
            "version": version,
            "content_hash": content_hash,
            "registered_at": _now_iso(),
            "author": author,
            "source": source,
        }

        scenario_path = self._scenario_path(scenario.id)
        scenario_path.write_text(
            json.dumps(scenario.to_dict(), indent=2), encoding="utf-8"
        )

        self._index[scenario.id] = entry
        self._save_index()
        return entry

    def get(self, scenario_id: str) -> Scenario | None:
        """Load a scenario from the registry by ID."""
        path = self._scenario_path(scenario_id)
        if not path.exists():
            return None
        return load_scenario(path)

    def get_entry(self, scenario_id: str) -> dict[str, Any] | None:
        """Return the registry metadata for a scenario."""
        return self._index.get(scenario_id)

    def list_all(
        self,
        tags: list[str] | None = None,
        domain: str = "",
    ) -> list[dict[str, Any]]:
        """List all registered scenarios, optionally filtered by tags or domain."""
        results: list[dict[str, Any]] = []
        for entry in self._index.values():
            if tags:
                entry_tags = set(entry.get("tags", []))
                if not entry_tags & set(tags):
                    continue
            if domain:
                entry_domain = entry.get("metadata", {}).get("domain", "")
                if entry_domain != domain:
                    continue
            results.append(entry)
        return sorted(results, key=lambda e: e["id"])

    def search(self, query: str) -> list[dict[str, Any]]:
        """Full-text search across scenario IDs, descriptions, and tags."""
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for entry in self._index.values():
            searchable = " ".join([
                entry.get("id", ""),
                entry.get("description", ""),
                " ".join(entry.get("tags", [])),
            ]).lower()
            if query_lower in searchable:
                results.append(entry)
        return sorted(results, key=lambda e: e["id"])

    def remove(self, scenario_id: str) -> bool:
        """Remove a scenario from the registry."""
        if scenario_id not in self._index:
            return False
        path = self._scenario_path(scenario_id)
        if path.exists():
            path.unlink()
        del self._index[scenario_id]
        self._save_index()
        return True

    def export_pack(self, output_dir: str, tags: list[str] | None = None) -> int:
        """Export matching scenarios to a directory for sharing."""
        entries = self.list_all(tags=tags)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        count = 0
        for entry in entries:
            scenario = self.get(entry["id"])
            if scenario is None:
                continue
            filepath = out / f"{scenario.id}.json"
            filepath.write_text(
                json.dumps(scenario.to_dict(), indent=2), encoding="utf-8"
            )
            count += 1
        return count

    def import_directory(
        self, directory: str, author: str = "", source: str = ""
    ) -> int:
        """Import all scenario files from a directory into the registry."""
        dir_path = Path(directory)
        if not dir_path.is_dir():
            raise FileNotFoundError(f"Directory not found: {directory}")

        count = 0
        for path in sorted(dir_path.rglob("*")):
            if path.suffix not in (".json", ".yaml", ".yml") or not path.is_file():
                continue
            try:
                scenario = load_scenario(path)
                self.register(scenario, author=author, source=source or str(path))
                count += 1
            except (ValueError, KeyError) as exc:
                logger.warning("Skipping %s: %s", path, exc)
        return count

    @property
    def count(self) -> int:
        return len(self._index)

    def _scenario_path(self, scenario_id: str) -> Path:
        safe = scenario_id.replace("/", "_").replace("\\", "_")
        return self._base / f"{safe}.json"

    def _index_path(self) -> Path:
        return self._base / self._INDEX_FILE

    def _load_index(self) -> dict[str, dict[str, Any]]:
        path = self._index_path()
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_index(self) -> None:
        path = self._index_path()
        path.write_text(json.dumps(self._index, indent=2), encoding="utf-8")


def _hash_scenario(scenario: Scenario) -> str:
    """Content-addressable hash for change detection."""
    content = json.dumps(scenario.to_dict(), sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
