"""Bind review requests to a saved, immutable annual chart or matrix."""
import hashlib
import json


SOURCES = {"audit_trend_robustness": ("analyze_patent_trend", "yearly_trend"),
           "search_gap_counterevidence": ("analyze_tech_matrix", "tech_effect_matrix")}


def digest(result):
    metadata = result.get("result_metadata", {})
    selected = {key:result[key] for key in ("result_type","data","functions","effects","matrix","gap_recommendations","provenance") if key in result}
    selected["metadata"] = {key:metadata.get(key) for key in
        ("parameters","scope","evidence_bins","sample_size","population_size","date_basis","count_unit")}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, ensure_ascii=False, separators=(",",":"),
                                     default=str).encode()).hexdigest()


def stamp(result):
    provenance = result.get("provenance") or {}
    if (result.get("result_type") in {"yearly_trend","tech_effect_matrix"}
            and provenance.get("dataset_version_id") and provenance.get("dataset_content_hash")
            and isinstance(provenance.get("parameters"), dict)
            and not (result.get("result_metadata") or {}).get("review_digest")):
        result.setdefault("result_metadata", {})["review_digest"] = digest(result)


def bind_review(tool_name, execution, session_id, snapshot, client_digest, supplied):
    if not execution or not session_id or execution.get("session_id") != session_id:
        raise ValueError("source_execution_unavailable")
    source = execution.get("result") or {}
    meta = source.get("result_metadata") or {}
    provenance = source.get("provenance") or {}
    expected = SOURCES.get(tool_name)
    if expected != (execution.get("tool_name"),source.get("result_type")):
        raise ValueError("source_execution_type_mismatch")
    if execution["status"] != "completed" or execution.get("stale"):
        raise ValueError("source_execution_stale")
    if (snapshot.version_id,snapshot.content_hash) != (provenance.get("dataset_version_id"),provenance.get("dataset_content_hash")):
        raise ValueError("source_dataset_changed")
    if not client_digest or digest(source) != client_digest or meta.get("review_digest") != client_digest:
        raise ValueError("source_result_changed")
    params = dict(supplied)
    info = {"execution_id":execution["id"], "sha256":client_digest, "source_tool":execution["tool_name"]}
    inherited = {"scope":provenance.get("scope") or {}}
    if tool_name=="audit_trend_robustness":
        old = provenance.get("parameters", {})
        inherited.update({key:old[key] for key in ("date_basis","year_start","year_end","applicant_filter","ipc_filter") if old.get(key) is not None})
        inherited.setdefault("date_basis", meta.get("date_basis","publication"))
        years = [int(row["year"]) for row in source["data"]]
        if years:
            inherited.setdefault("year_start", min(years))
            inherited.setdefault("year_end", max(years))
        if set(params)-{"example_limit"}:
            raise ValueError("source_filters_are_fixed")
    else:
        if "scope" in params:
            raise ValueError("source_filters_are_fixed")
        pair = params.get("technology"), params.get("effect")
        observed = None
        for candidate in source.get("gap_recommendations", []):
            if pair==(candidate["function"],candidate["effect"]):
                observed=candidate["patent_count"]
                break
        if observed is None and pair[0] in source["functions"] and pair[1] in source["effects"]:
            observed=source["matrix"][source["functions"].index(pair[0])][source["effects"].index(pair[1])]
        if observed is None:
            raise ValueError("unknown_matrix_pair")
        info.update(matrix_observed=observed, matrix_sample_size=meta.get("sample_size"),
                    matrix_population=meta.get("population_size"))
    return {**params, **inherited}, info
