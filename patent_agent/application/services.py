"""Small use-case boundaries used by HTTP and MCP transports."""

from __future__ import annotations

from typing import Any, Awaitable, Callable


class DatasetService:
    def __init__(self, loader: Callable[[str], Any]):
        self._loader = loader

    def load(self, input_dir: str):
        return self._loader(input_dir)


class AnalysisService:
    async def run_tool(self, tool: Any, dataset: Any, params: dict[str, Any]):
        return await tool.run(dataset, **params)


class ReportService:
    def __init__(self, generator_factory: Callable[[], Any]):
        self._generator_factory = generator_factory

    def export_html(self, title: str, messages: list[dict[str, Any]]) -> str:
        generator = self._generator_factory()
        for message in messages:
            if message.get("content"):
                generator.add_section(message.get("role", "assistant"), message["content"])
        return generator.generate_html(title=title)
