"""CPU tools run off-loop with bounded runtime and input contracts."""

import asyncio
import time

import pandas as pd
import pytest

from models.analysis_results import AnalysisResult
from storage.datastore import PatentDataStore
from tools.base import Tool


class _BusyTool(Tool):
    name = "runtime_contract_test"
    description = "test"
    allow_empty = True
    max_execution_seconds = 1
    parameters = {"delay": {"type": "number", "default": 0.12}}

    @property
    def evidence_record(self):
        return {
            "algorithm_id": "runtime_contract", "version": "1",
            "evidence_type": "descriptive_statistic", "fields": {},
            "sources": [], "conditions": [], "prohibited_claims": [],
        }

    async def execute(self, storage, delay: float = 0.12):
        time.sleep(delay)
        return AnalysisResult(result_type="runtime_contract", summary="done")


def test_cpu_tool_does_not_block_event_loop():
    async def scenario():
        tool = _BusyTool()
        task = asyncio.create_task(tool.run(PatentDataStore(), delay=0.12))
        started = time.perf_counter()
        await asyncio.sleep(0.02)
        tick_elapsed = time.perf_counter() - started
        result = await task
        return tick_elapsed, result

    tick_elapsed, result = asyncio.run(scenario())
    assert tick_elapsed < 0.08
    assert result.result_metadata["runtime_limits"]["cpu_offloaded"] is True


def test_cancelled_worker_result_is_not_returned_as_success():
    async def scenario():
        task = asyncio.create_task(_BusyTool().run(PatentDataStore(), delay=0.2))
        await asyncio.sleep(0.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_record_limit_requires_scope_reduction():
    tool = _BusyTool()
    tool.max_input_records = 1
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["P1", "P2"], "title": ["a", "b"],
    }))
    with pytest.raises(ValueError, match="超过上限"):
        asyncio.run(tool.run(store, delay=0))
