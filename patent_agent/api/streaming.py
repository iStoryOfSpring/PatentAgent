"""Application-owned lifetime boundary for Agent HTTP streams."""
import logging
import anyio
from fastapi.responses import StreamingResponse

logger = logging.getLogger("patentagent.streaming")


class AgentStreamingResponse(StreamingResponse):
    def __init__(self, content, *, container, turn_id, finalize, **kwargs):
        super().__init__(content, **kwargs)
        self.container = container
        self.turn_id = turn_id
        self.finalize = finalize

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                # Never shield a streaming yield; only finalization owns this scope.
                with anyio.CancelScope(shield=True):
                    try:
                        close = getattr(self.body_iterator, "aclose", None)
                        if close is not None:
                            await close()
                    except BaseException:
                        logger.warning("agent_stream.iterator_cleanup_failed")
                    try:
                        await self.finalize()
                    except BaseException:
                        logger.warning("agent_stream.persistence_cleanup_failed")
            finally:
                # Capture the application container at request entry, not delayed context.
                self.container.active_generation_turns.discard(self.turn_id)
