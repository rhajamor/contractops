"""Baseline lifecycle management: approve, expire, rotate, compare-to-last-approved.

Extends the baseline storage layer with lifecycle states (draft, approved,
expired, rotated) and version history, enabling governance workflows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from contractops.storage import BaselineStorage

logger = logging.getLogger("contractops.lifecycle")


class BaselineLifecycle:
    """Manages lifecycle states and versioning on top of a storage backend."""

    STATES = ("draft", "approved", "expired", "rotated")
    _META_SUFFIX = "__lifecycle"

    def __init__(self, storage: BaselineStorage) -> None:
        self._storage = storage

    def approve(self, scenario_id: str, approver: str = "") -> dict[str, Any]:
        """Mark the current baseline as approved for release gating."""
        meta = self._load_or_create_meta(scenario_id)
        version = meta.get("version", 0) + 1

        if meta.get("state") == "approved":
            meta["history"].append({
                "version": meta["version"],
                "state": "rotated",
                "rotated_at": _now_iso(),
                "rotated_by": approver,
            })

        meta.update({
            "state": "approved",
            "version": version,
            "approved_at": _now_iso(),
            "approved_by": approver,
            "expired_at": None,
        })
        self._save_meta(scenario_id, meta)
        logger.info("Baseline '%s' approved (v%d) by %s", scenario_id, version, approver)
        return meta

    def expire(self, scenario_id: str, reason: str = "") -> dict[str, Any]:
        """Mark a baseline as expired so it is no longer used for gating."""
        meta = self._load_or_create_meta(scenario_id)
        meta.update({
            "state": "expired",
            "expired_at": _now_iso(),
            "expire_reason": reason,
        })
        meta["history"].append({
            "version": meta.get("version", 0),
            "state": "expired",
            "expired_at": meta["expired_at"],
            "reason": reason,
        })
        self._save_meta(scenario_id, meta)
        logger.info("Baseline '%s' expired: %s", scenario_id, reason)
        return meta

    def rotate(self, scenario_id: str, approver: str = "") -> dict[str, Any]:
        """Rotate: expire the current baseline and promote the latest draft."""
        meta = self._load_or_create_meta(scenario_id)
        if meta.get("state") == "approved":
            meta["history"].append({
                "version": meta.get("version", 0),
                "state": "rotated",
                "rotated_at": _now_iso(),
            })
        return self.approve(scenario_id, approver=approver)

    def get_state(self, scenario_id: str) -> dict[str, Any]:
        """Return the current lifecycle metadata for a baseline."""
        return self._load_or_create_meta(scenario_id)

    def is_approved(self, scenario_id: str) -> bool:
        meta = self._load_or_create_meta(scenario_id)
        return meta.get("state") == "approved"

    def list_versions(self, scenario_id: str) -> list[dict[str, Any]]:
        """Return the full version history for a baseline."""
        meta = self._load_or_create_meta(scenario_id)
        return meta.get("history", [])

    def _meta_key(self, scenario_id: str) -> str:
        safe = scenario_id.replace("/", "_").replace("\\", "_")
        return f"{safe}{self._META_SUFFIX}"

    def _load_or_create_meta(self, scenario_id: str) -> dict[str, Any]:
        key = self._meta_key(scenario_id)
        if self._storage.exists(key):
            return self._storage.load(key)
        return {
            "scenario_id": scenario_id,
            "state": "draft",
            "version": 0,
            "approved_at": None,
            "approved_by": None,
            "expired_at": None,
            "expire_reason": None,
            "history": [],
        }

    def _save_meta(self, scenario_id: str, meta: dict[str, Any]) -> None:
        key = self._meta_key(scenario_id)
        self._storage.save(key, meta)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compare_baselines(
    storage: BaselineStorage,
    scenario_id: str,
) -> dict[str, Any] | None:
    """Compare the stored baseline with lifecycle metadata.

    Returns enriched comparison data if a baseline exists.
    """
    from contractops.baseline import baseline_key

    key = baseline_key(scenario_id)
    if not storage.exists(key):
        return None

    baseline_data = storage.load(key)
    lifecycle = BaselineLifecycle(storage)
    meta = lifecycle.get_state(scenario_id)

    return {
        "scenario_id": scenario_id,
        "has_baseline": True,
        "lifecycle_state": meta.get("state", "draft"),
        "version": meta.get("version", 0),
        "approved_at": meta.get("approved_at"),
        "approved_by": meta.get("approved_by"),
        "baseline_saved_at": baseline_data.get("saved_at"),
        "executor": baseline_data.get("run_result", {}).get("executor"),
    }
