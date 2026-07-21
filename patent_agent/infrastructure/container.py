"""Application-owned runtime state and injectable dependencies."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from patent_agent.security import CredentialVault


@dataclass
class AppContainer:
    settings: Any
    store: Any = None
    agent: Any = None
    conversation_store: Any = None
    provider_store: Any = None
    dataset_service: Any = None
    analysis_service: Any = None
    report_service: Any = None
    sessions: dict[str, Any] = field(default_factory=dict)
    credential_vault: CredentialVault = field(default_factory=CredentialVault)
    connected_profile_id: str | None = None
    connected_profile_snapshot: dict | None = None
    llm_capabilities: dict = field(default_factory=dict)
    profiles_needing_reconnect: set[str] = field(default_factory=set)
    profile_probe_states: dict[str, dict] = field(default_factory=dict)
    active_generation_turns: set[str] = field(default_factory=set)
    tool_semaphore: asyncio.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        self.tool_semaphore = asyncio.Semaphore(self.settings.max_tool_concurrency)

    def clear_ephemeral(self) -> None:
        self.credential_vault.clear()
        self.profile_probe_states.clear()
        self.profiles_needing_reconnect.clear()
        self.active_generation_turns.clear()
        self.connected_profile_id = None
        self.connected_profile_snapshot = None
        self.llm_capabilities = {}
