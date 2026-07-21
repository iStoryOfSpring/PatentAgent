"""Process-memory-only credential storage with an intentionally small API."""

from __future__ import annotations

from copy import deepcopy


class CredentialVault:
    def __init__(self) -> None:
        self._entries: dict[str, dict] = {}

    def get(self, profile_id: str, default=None):
        value = self._entries.get(profile_id)
        return deepcopy(value) if value is not None else default

    def set(self, profile_id: str, credentials: dict) -> None:
        self._entries[profile_id] = deepcopy(credentials)

    def pop(self, profile_id: str, default=None):
        value = self._entries.pop(profile_id, default)
        return deepcopy(value)

    def clear(self) -> None:
        self._entries.clear()

    def has_api_key(self, profile_id: str) -> bool:
        return bool(self._entries.get(profile_id, {}).get("api_key"))

    def __len__(self) -> int:
        return len(self._entries)
