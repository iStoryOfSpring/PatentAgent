"""FastAPI dependency accessors for application-owned state."""

from fastapi import Request

from patent_agent.infrastructure import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container
