"""Application-owned runtime state and injectable dependencies."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from patent_agent.security import CredentialVault

if TYPE_CHECKING:
    from agent.orchestrator import PatentAgentOrchestrator
    from models.session import Session
    from patent_agent.application import (
        AnalysisService, ConversationService, DatasetImportService, ReportService,
        ProviderService, SearchIndexService, TaskService,
        ToolExecutionService,
    )
    from patent_agent.infrastructure.settings import AppSettings
    from storage.conversation_store import ConversationStore
    from storage.datastore import PatentDataStore
    from storage.provider_store import ProviderProfileStore


@dataclass
class AppContainer:
    settings: AppSettings
    store: PatentDataStore | None = None
    agent: PatentAgentOrchestrator | None = None
    conversation_store: ConversationStore | None = None
    conversation_service: ConversationService | None = None
    provider_store: ProviderProfileStore | None = None
    provider_service: ProviderService | None = None
    dataset_service: DatasetImportService | None = None
    analysis_service: AnalysisService | None = None
    tool_execution_service: ToolExecutionService | None = None
    report_service: ReportService | None = None
    search_index_service: SearchIndexService | None = None
    task_service: TaskService | None = None
    sessions: dict[str, Session] = field(default_factory=dict)
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
