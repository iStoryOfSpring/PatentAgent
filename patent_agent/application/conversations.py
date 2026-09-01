"""Conversation read-model normalization independent of HTTP routes."""

from agent.final_answer import user_facing_content


class ConversationService:
    """Conversation CRUD boundary shared by HTTP and future transports."""

    def __init__(self, repository):
        self.repository = repository

    async def create(
        self, name: str, dataset_fingerprint: str, dataset_version_id: str = "",
    ):
        return await self.repository.create_session(
            name, dataset_fingerprint, dataset_version_id=dataset_version_id,
        )

    async def list(self):
        return await self.repository.list_sessions()

    async def get(self, session_id: str, dataset_fingerprint: str = ""):
        return normalize_session_detail(
            await self.repository.get_session_detail(session_id)
        )

    async def bind_dataset(
        self, session_id: str, dataset_version_id: str, dataset_fingerprint: str,
    ):
        return await self.repository.bind_session_dataset(
            session_id, dataset_version_id, dataset_fingerprint,
        )

    async def rename(self, session_id: str, name: str):
        return await self.repository.rename_session(session_id, name)

    async def delete(self, session_id: str) -> None:
        await self.repository.delete_session(session_id)


def normalize_history_messages(messages: list[dict]) -> list[dict]:
    normalized_messages: list[dict] = []
    for stored in messages:
        item = dict(stored)
        if item.get("role") == "assistant":
            visible, canonical, mode = user_facing_content(str(item.get("content", "")))
            item["content"] = visible
            if canonical is not None:
                metadata = dict(item.get("metadata") or {})
                metadata["answer_format"] = "markdown"
                metadata["normalization_mode"] = mode
                if canonical.get("followup_suggestions"):
                    metadata["followup_suggestions"] = canonical["followup_suggestions"]
                    metadata["followup_questions"] = [
                        entry["text"] for entry in canonical["followup_suggestions"]
                    ]
                if canonical.get("evidence_refs"):
                    metadata.setdefault("evidence_refs", canonical["evidence_refs"])
                item["metadata"] = metadata
        normalized_messages.append(item)
    return normalized_messages


def normalize_session_detail(detail: dict) -> dict:
    normalized = dict(detail)
    normalized["messages"] = normalize_history_messages(detail.get("messages", []))
    turns = []
    for stored in detail.get("turns", []):
        turn = dict(stored)
        if turn.get("final_text"):
            turn["final_text"] = user_facing_content(str(turn["final_text"]))[0]
        turns.append(turn)
    normalized["turns"] = turns
    return normalized


def normalize_evidence_history(evidence: list[dict]) -> list[dict]:
    normalized = []
    for stored in evidence:
        item = dict(stored)
        if item.get("final_text"):
            item["final_text"] = user_facing_content(str(item["final_text"]))[0]
        normalized.append(item)
    return normalized
