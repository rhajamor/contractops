"""Authentication, authorization, and tenant isolation for enterprise deployments.

Provides role-based access control (RBAC), API key management, and tenant
boundaries for multi-team ContractOps environments.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("contractops.auth")


class Permission:
    READ = "read"
    WRITE = "write"
    APPROVE = "approve"
    ADMIN = "admin"

    ALL = {READ, WRITE, APPROVE, ADMIN}


ROLE_PERMISSIONS: dict[str, set[str]] = {
    "viewer": {Permission.READ},
    "developer": {Permission.READ, Permission.WRITE},
    "approver": {Permission.READ, Permission.WRITE, Permission.APPROVE},
    "admin": Permission.ALL.copy(),
}


class User:
    def __init__(
        self,
        user_id: str,
        email: str = "",
        role: str = "viewer",
        tenant_id: str = "default",
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.role = role
        self.tenant_id = tenant_id

    @property
    def permissions(self) -> set[str]:
        return ROLE_PERMISSIONS.get(self.role, set())

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "role": self.role,
            "tenant_id": self.tenant_id,
        }


class AuthManager:
    """File-backed auth manager for enterprise deployments."""

    def __init__(self, auth_dir: str = ".contractops/auth") -> None:
        self._dir = Path(auth_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._users_file = self._dir / "users.json"
        self._keys_file = self._dir / "api_keys.json"
        self._users = self._load_json(self._users_file)
        self._api_keys = self._load_json(self._keys_file)

    def create_user(
        self,
        user_id: str,
        email: str = "",
        role: str = "viewer",
        tenant_id: str = "default",
    ) -> User:
        if role not in ROLE_PERMISSIONS:
            raise ValueError(
                f"Invalid role: {role}. Available: {', '.join(ROLE_PERMISSIONS.keys())}"
            )
        user = User(user_id=user_id, email=email, role=role, tenant_id=tenant_id)
        self._users[user_id] = user.to_dict()
        self._save_json(self._users_file, self._users)
        return user

    def get_user(self, user_id: str) -> User | None:
        data = self._users.get(user_id)
        if data is None:
            return None
        return User(**data)

    def update_role(self, user_id: str, new_role: str) -> User | None:
        if new_role not in ROLE_PERMISSIONS:
            raise ValueError(f"Invalid role: {new_role}")
        if user_id not in self._users:
            return None
        self._users[user_id]["role"] = new_role
        self._save_json(self._users_file, self._users)
        return self.get_user(user_id)

    def delete_user(self, user_id: str) -> bool:
        if user_id not in self._users:
            return False
        del self._users[user_id]
        self._save_json(self._users_file, self._users)
        return True

    def list_users(self, tenant_id: str = "") -> list[dict[str, Any]]:
        users = list(self._users.values())
        if tenant_id:
            users = [u for u in users if u.get("tenant_id") == tenant_id]
        return sorted(users, key=lambda u: u["user_id"])

    def generate_api_key(self, user_id: str, description: str = "") -> str:
        """Generate a new API key for a user."""
        if user_id not in self._users:
            raise ValueError(f"User not found: {user_id}")

        raw_key = secrets.token_urlsafe(32)
        key_hash = _hash_key(raw_key)

        self._api_keys[key_hash] = {
            "user_id": user_id,
            "description": description,
            "created_at": _now_iso(),
            "active": True,
        }
        self._save_json(self._keys_file, self._api_keys)
        return raw_key

    def authenticate_key(self, api_key: str) -> User | None:
        """Authenticate by API key and return the associated user."""
        key_hash = _hash_key(api_key)
        key_data = self._api_keys.get(key_hash)
        if key_data is None or not key_data.get("active"):
            return None
        return self.get_user(key_data["user_id"])

    def revoke_key(self, api_key: str) -> bool:
        key_hash = _hash_key(api_key)
        if key_hash not in self._api_keys:
            return False
        self._api_keys[key_hash]["active"] = False
        self._save_json(self._keys_file, self._api_keys)
        return True

    def check_authorization(
        self,
        user: User,
        permission: str,
        tenant_id: str = "",
    ) -> bool:
        """Check if a user has a specific permission within a tenant."""
        if tenant_id and user.tenant_id != tenant_id:
            return False
        return user.has_permission(permission)

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_json(self, path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
