import asyncio
import json
import sqlite3
from types import SimpleNamespace
import pandas as pd
import pytest
from tools import tool_registry
from storage.datastore import PatentDataStore
from patent_agent.application import monitoring


def store():
    value=PatentDataStore(pd.DataFrame({"patent_number":["US1A1"],"title":["battery"],"abstract":["cell"],"publication_date":["2020-01-01"],"applicants":["Acme;Beta"],"family_members":["EP1A1;JP1A"],"legal_events_json":["[]"]}))
    value._adapter_name="wos";value._dataset_id_override="dataset_synthetic";value._version_id_override="version_synthetic";return value

@pytest.fixture
def setup_monitor(tmp_path,monkeypatch):
    path=tmp_path/"untouched"/"monitor.sqlite";monkeypatch.setenv("PATENTAGENT_MONITOR_DB",str(path))
    from tools import search_tool
    monkeypatch.setattr(search_tool,"_get_searcher",lambda *a,**k:SimpleNamespace(hybrid_search=lambda **kw:[SimpleNamespace(patent_number="US1A1")]))
    return path,store(),tool_registry.get_tool("monitor_patent_changes"),{"strategy_id":"s","strategy_version":1,"query":"battery","update_baseline":True}

def approve_run(tool,value,params):
    with monitoring.approved_calls([{"name":tool.name,"arguments":params}],value,{"0":monitoring.baseline_identity(params,value)}):
        return asyncio.run(tool.run(value,**params))

def test_preview_creates_no_files_and_direct_transports_cannot_write(setup_monitor):
    path,value,tool,params=setup_monitor
    preview=asyncio.run(tool.run(value,**{**params,"update_baseline":False}))
    assert preview.result_metadata["baseline_updated"] is False
    assert not path.parent.exists()
    with pytest.raises(PermissionError,match="monitor_approval_required"):asyncio.run(tool.run(value,**params))
    with pytest.raises(PermissionError):asyncio.run(tool.execute(value,**params))
    assert not path.parent.exists()
    assert preview.data[0]["event_type"]=="first_observed" and preview.data[0]["before"] is None


def test_stale_parameters_dataset_and_baseline_invalidate_approval(setup_monitor):
    path,value,tool,params=setup_monitor
    baselines={"0":monitoring.baseline_identity(params,value)}
    with monitoring.approved_calls([{"name":tool.name,"arguments":params}],value,baselines):
        with pytest.raises(PermissionError):asyncio.run(tool.run(value,**{**params,"top_k":20}))
        value._version_id_override="different"
        with pytest.raises(PermissionError):asyncio.run(tool.run(value,**params))
    value._version_id_override="version_synthetic"
    approve_run(tool,value,params)
    with monitoring.approved_calls([{"name":tool.name,"arguments":params}],value,baselines):
        with pytest.raises(PermissionError):asyncio.run(tool.run(value,**params))


def test_approval_is_rechecked_against_transaction_actual_row(setup_monitor,monkeypatch):
    path,value,tool,params=setup_monitor
    approve_run(tool,value,params)
    captured=monitoring.baseline_identity(params,value)
    original=monitoring.read_baseline;reads=0
    def racing_read(params,value):
        nonlocal reads
        reads+=1
        if reads==2:
            with sqlite3.connect(path) as db:db.execute("UPDATE monitor_baselines_v3 SET updated_at='synthetic-concurrent-change'")
        return original(params,value)
    monkeypatch.setattr(monitoring,"read_baseline",racing_read)
    with monitoring.approved_calls([{"name":tool.name,"arguments":params}],value,{"0":captured}):
        with pytest.raises(PermissionError,match="baseline changed"):asyncio.run(tool.run(value,**params))
    with sqlite3.connect(path) as db:assert db.execute("SELECT updated_at FROM monitor_baselines_v3").fetchone()[0]=="synthetic-concurrent-change"


def test_threshold_and_empty_baseline_existence_and_normalized_lists(setup_monitor):
    path,value,tool,params=setup_monitor
    first=approve_run(tool,value,params)
    value.get_all().loc[0,"applicants"]="Beta;Acme"
    value.get_all().loc[0,"family_members"]="JP1A;EP1A1"
    second=asyncio.run(tool.run(value,**{**params,"update_baseline":False}))
    assert second.data==[]
    value.get_all().loc[0,"applicants"]="Changed"
    threshold=asyncio.run(tool.run(value,**{**params,"update_baseline":False,"notification_policy":"threshold","minimum_event_count":2}))
    assert len(threshold.data)==1 and threshold.result_metadata["should_notify"] is False
    assert threshold.data[0]["before"]["applicants"]==["Acme","Beta"]
    with sqlite3.connect(path) as db:db.execute("UPDATE monitor_baselines_v3 SET snapshot_json='{}'")
    empty=asyncio.run(tool.run(value,**{**params,"update_baseline":False}))
    assert empty.result_metadata["baseline_existed"] is True
    assert empty.data[0]["event_type"]=="entered_returned_set"
    assert first.result_metadata["run_id"]!=empty.result_metadata["run_id"]


def test_partial_source_cannot_advance_and_strategy_changes_need_version(setup_monitor):
    _,value,tool,params=setup_monitor
    value._import_report={"matched_set_complete":False}
    with pytest.raises(ValueError,match="partial"):approve_run(tool,value,params)
    value._import_report={}
    approve_run(tool,value,params)
    with pytest.raises(ValueError,match="strategy_definition_conflict"):
        approve_run(tool,value,{**params,"query":"changed"})


def test_scoped_write_keeps_parent_dataset_version_in_approval(setup_monitor):
    _,value,tool,params=setup_monitor
    value._version_id_override=""  # Directly loaded production stores also derive their version from content.
    result=approve_run(tool,value,{**params,"scope":{"patent_numbers":["US1A1"]}})
    assert result.result_metadata["baseline_updated"] is True
    assert result.result_metadata["definition"]["scope"]=={"patent_numbers":["US1A1"]}
