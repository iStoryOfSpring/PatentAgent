"""Server-owned monitor approvals and side-effect-free baseline previews."""
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

run_parameters: ContextVar[dict | None] = ContextVar("monitor_run_parameters", default=None)

def canonical_params(params):
    return {"strategy_id":params["strategy_id"],"strategy_version":params["strategy_version"],"query":params["query"].strip(),"top_k":params.get("top_k",500),"update_baseline":params.get("update_baseline",False),"notification_policy":params.get("notification_policy","all_changes"),"minimum_event_count":params.get("minimum_event_count",1),"scope":params.get("scope",{})}

_approvals: ContextVar[frozenset[str]] = ContextVar("monitor_approvals", default=frozenset())

def approval_key(tool, params, dataset_version, baseline_version):
    return hashlib.sha256(json.dumps([tool, canonical_params(params), dataset_version, baseline_version], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

@contextmanager
def approved_calls(calls, storage, baselines=None):
    """Only the application invokes this after persisted, exact-plan confirmation."""
    keys = []
    from tools import tool_registry
    for index, call in enumerate(calls):
        name = call.get("tool_name") or call.get("name")
        try: tool = tool_registry.get_tool(name)
        except KeyError: continue
        if name == "monitor_patent_changes" and tool:
            params = tool.validate_params(call.get("params") or call.get("arguments") or call.get("parameters") or {})
            keys.append(approval_key(name, params, storage.snapshot().version_id, (baselines or {}).get(str(index), "unapproved")))
    token = _approvals.set(frozenset(keys))
    try:
        yield
    finally:
        _approvals.reset(token)

def baseline_path():
    return Path(os.getenv("PATENTAGENT_MONITOR_DB", ".patentagent/monitoring.db")).resolve()

def namespace(storage):
    return hashlib.sha256(json.dumps([storage.snapshot().dataset_id, storage.adapter_name]).encode()).hexdigest()

def read_baseline(params, storage):
    path = baseline_path()
    if not path.is_file():
        return None
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='monitor_baselines_v3'").fetchone():
            return None
        return db.execute("SELECT definition_json,snapshot_json,dataset_hash,updated_at FROM monitor_baselines_v3 WHERE namespace=? AND strategy_id=? AND strategy_version=?", (namespace(storage), params["strategy_id"], params["strategy_version"])).fetchone()

def row_identity(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()

def baseline_identity(params, storage):
    return row_identity(read_baseline(params, storage))

def require_write_approval(params, storage):
    if approval_key("monitor_patent_changes", params, storage.snapshot().version_id, baseline_identity(params, storage)) not in _approvals.get():
        raise PermissionError("monitor_approval_required: 请通过 Agent 确认具体策略、参数、数据版本和基线后写入；REST/MCP 参数不能授权")

async def monitor(tool, storage, params):
    from tools.search_tool import _get_searcher
    from models.analysis_results import GenericAnalysisResult
    import pandas as pd
    clean = canonical_params(run_parameters.get() or tool.validate_params(params))
    update = clean.get("update_baseline", False)
    if update:
        require_write_approval(clean, storage)
        if storage._import_report.get("matched_set_complete") is False:
            raise ValueError("partial acquisition cannot advance monitor baseline")
    definition = {"dataset_id": storage.snapshot().dataset_id, "source": storage.adapter_name,
        "query": clean["query"].strip(), "top_k": clean.get("top_k", 500), "scope": clean.get("scope", {}), "strategy_version": clean["strategy_version"]}
    definition_json = json.dumps(definition, sort_keys=True, ensure_ascii=False)
    row = read_baseline(clean, storage)
    if row is not None and row[0] != definition_json:
        raise ValueError("strategy_definition_conflict: 同版本策略定义不能修改，请增加 strategy_version")
    before = json.loads(row[1]) if row is not None else {}
    snapshot = {}
    frame = storage.get_all().set_index("patent_number", drop=False)
    for item in _get_searcher(storage).hybrid_search(query=clean["query"], top_k=clean.get("top_k", 500)):
        record = frame.loc[item.patent_number]
        if isinstance(record, pd.DataFrame): record = record.iloc[0]
        fields = {}
        for key in ("family_members", "backward_citations", "forward_citations", "legal_events_json", "applicants"):
            value = record.get(key, "")
            if isinstance(value, str):
                if key.endswith("_json"):
                    try: value = json.loads(value or "[]")
                    except ValueError: value = [value]
                else: value = [v.strip() for v in value.split(";") if v.strip()]
            if not isinstance(value, list): value = []
            fields[key] = sorted(value, key=lambda x: json.dumps(x, sort_keys=True))
        snapshot[item.patent_number] = fields
    now = datetime.now(timezone.utc).isoformat()
    events = []
    for number in sorted(set(snapshot) | set(before)):
        left, right = before.get(number), snapshot.get(number)
        if left == right: continue
        events.append({"patent_number": number, "event_type": ("first_observed" if row is None else "entered_returned_set") if left is None else "no_longer_returned" if right is None else "fields_changed", "before": left, "after": right, "before_observed_at": row[3] if row else None, "observed_at": now})
    run_id = hashlib.sha256(json.dumps([definition, before, snapshot, row[2] if row else None, storage.dataset_fingerprint()], sort_keys=True).encode()).hexdigest()
    if update:
        path = baseline_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS monitor_baselines_v3(namespace TEXT,strategy_id TEXT,strategy_version INTEGER,definition_json TEXT,snapshot_json TEXT,dataset_hash TEXT,updated_at TEXT,PRIMARY KEY(namespace,strategy_id,strategy_version))")
            db.execute("CREATE TABLE IF NOT EXISTS monitor_runs_v2(run_id TEXT PRIMARY KEY,payload_json TEXT,created_at TEXT)")
            # Revalidate after obtaining the SQLite write lock to prevent stale approvals.
            db.execute("BEGIN IMMEDIATE")
            actual = db.execute("SELECT definition_json,snapshot_json,dataset_hash,updated_at FROM monitor_baselines_v3 WHERE namespace=? AND strategy_id=? AND strategy_version=?", (namespace(storage), clean["strategy_id"], clean["strategy_version"])).fetchone()
            actual_approval = approval_key("monitor_patent_changes", clean, storage.snapshot().version_id, row_identity(actual))
            if actual_approval not in _approvals.get():
                raise PermissionError("monitor_approval_required: baseline changed after confirmation")
            if actual != row: raise ValueError("baseline_version_conflict: 基线已变化，请重新确认")
            db.execute("INSERT OR IGNORE INTO monitor_runs_v2 VALUES (?,?,?)", (run_id,json.dumps(events, ensure_ascii=False),now))
            db.execute("INSERT OR REPLACE INTO monitor_baselines_v3 VALUES (?,?,?,?,?,?,?)", (namespace(storage),clean["strategy_id"],clean["strategy_version"],definition_json,json.dumps(snapshot, sort_keys=True),storage.dataset_fingerprint(),now))
    return GenericAnalysisResult(result_type="patent_monitor",data=events,summary=f"策略 {clean['strategy_id']} 检测到 {len(events)} 个返回集变化事件。", result_metadata={"run_id":run_id,"strategy_id":clean["strategy_id"],"strategy_version":clean["strategy_version"],"strategy_hash":hashlib.sha256(definition_json.encode()).hexdigest(),"baseline_existed":row is not None,"baseline_updated":update,"returned_count":len(snapshot),"analyzed_record_count":len(frame),"should_notify":row is not None and (bool(events) if clean["notification_policy"] == "all_changes" else len(events) >= clean["minimum_event_count"]),"notification_policy":clean["notification_policy"],"minimum_event_count":clean["minimum_event_count"],"definition":definition},warnings=["首次观测和进入返回集不等于新公开；变化不是侵权结论。"])
