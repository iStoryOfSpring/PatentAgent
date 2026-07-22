"""FastAPI route modules for the modular monolith."""

from .datasets import router as datasets_router
from .reports import router as reports_router
from .providers import router as providers_router
from .sessions import router as sessions_router
from .tools import router as tools_router
from .tasks import router as tasks_router

__all__ = [
    "datasets_router", "providers_router", "reports_router", "sessions_router",
    "tools_router",
    "tasks_router",
]
