"""Baseline capture, persistence, and comparison.

Uses the storage abstraction layer for backend-agnostic persistence.
Supports both string-diff similarity and embedding-based semantic similarity.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from typing import Any

from contractops.models import RunResult
from contractops.storage import BaselineStorage

logger = logging.getLogger("contractops.baseline")


def baseline_key(scenario_id: str) -> str:
    return scenario_id.replace("/", "_").replace("\\", "_")


def baseline_path(baseline_dir: str, scenario_id: str) -> Path:
    """Legacy helper for file-path-based workflows."""
    safe_id = baseline_key(scenario_id)
    return Path(baseline_dir) / f"{safe_id}.json"


def save_baseline(
    result: RunResult,
    storage: BaselineStorage | None = None,
    path: Path | None = None,
) -> str:
    """Save a baseline run result.

    Provide *storage* for backend-agnostic persistence, or *path* for direct
    file output (backwards compatible).
    """
    payload = _build_payload(result)

    if storage is not None:
        key = baseline_key(result.scenario_id)
        return storage.save(key, payload)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    raise ValueError("Provide either storage or path argument.")


def load_baseline(
    scenario_id: str | None = None,
    storage: BaselineStorage | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Load a saved baseline."""
    if storage is not None:
        if scenario_id is None:
            raise ValueError("scenario_id required when using storage backend.")
        key = baseline_key(scenario_id)
        return storage.load(key)

    if path is not None:
        import json

        return json.loads(path.read_text(encoding="utf-8"))

    raise ValueError("Provide either storage or path argument.")


def baseline_exists(
    scenario_id: str | None = None,
    storage: BaselineStorage | None = None,
    path: Path | None = None,
) -> bool:
    if storage is not None and scenario_id is not None:
        key = baseline_key(scenario_id)
        return storage.exists(key)
    if path is not None:
        return path.exists()
    return False


def compare_outputs(
    baseline_output: str,
    candidate_output: str,
    max_diff_lines: int = 14,
    use_semantic: bool = False,
    embed_model: str = "",
    embed_url: str = "",
) -> dict[str, Any]:
    """Compare baseline and candidate outputs.

    When *use_semantic* is True, computes embedding-based cosine similarity
    via Ollama in addition to the string-diff similarity (which is kept for
    explainability). The semantic score becomes the primary similarity metric.
    """
    string_similarity = SequenceMatcher(
        None,
        _normalize(baseline_output),
        _normalize(candidate_output),
    ).ratio()

    diff_lines = list(
        unified_diff(
            baseline_output.splitlines(),
            candidate_output.splitlines(),
            fromfile="baseline",
            tofile="candidate",
            lineterm="",
        )
    )
    preview = diff_lines[:max_diff_lines]

    result: dict[str, Any] = {
        "string_similarity": round(string_similarity, 6),
        "diff_preview": preview,
        "diff_truncated": len(diff_lines) > max_diff_lines,
    }

    if use_semantic:
        try:
            from contractops.embeddings import semantic_similarity

            kwargs: dict[str, str] = {}
            if embed_model:
                kwargs["model"] = embed_model
            if embed_url:
                kwargs["base_url"] = embed_url
            sem_sim = semantic_similarity(baseline_output, candidate_output, **kwargs)
            result["semantic_similarity"] = round(sem_sim, 6)
            result["similarity"] = result["semantic_similarity"]
        except Exception as exc:
            logger.warning("Semantic similarity failed, falling back to string: %s", exc)
            result["similarity"] = result["string_similarity"]
    else:
        result["similarity"] = result["string_similarity"]

    return result


def _build_payload(result: RunResult) -> dict[str, Any]:
    return {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "run_result": asdict(result),
    }


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())
