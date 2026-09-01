import pandas as pd

from engine.entity_resolution import normalize_entity_key, resolve_entity
from storage.datastore import PatentDataStore


def test_corporate_suffix_and_unicode_variants_share_stable_entity():
    first = resolve_entity("ＡＣＭＥ Corporation")
    second = resolve_entity("Acme Corp.")
    assert first.entity_id == second.entity_id
    assert first.canonical_name == second.canonical_name == "ACME"
    assert normalize_entity_key("示例科技有限公司") == "示例科技"


def test_store_preserves_raw_names_and_adds_reversible_entity_columns():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["P1", "P2"],
        "title": ["x", "y"],
        "abstract": ["x", "y"],
        "date": ["2024-01-01", "2024-01-01"],
        "applicants": ["ACME Corporation", "Acme Corp."],
        "inventors": ["Li Wei", "Li Wei"],
        "ipc": ["H01M", "H01M"],
    }))
    frame = store.get_all()
    assert list(frame["applicants"]) == ["ACME Corporation", "Acme Corp."]
    assert frame["applicant_entity_ids"].nunique() == 1
    assert set(frame["applicant_canonical_names"]) == {"ACME"}
    assert store.get_summary().top_applicants[0] == ("ACME", 2)


def test_entity_id_scope_works_after_automatic_mapping():
    store = PatentDataStore(pd.DataFrame({
        "patent_number": ["P1", "P2"], "title": ["x", "y"],
        "abstract": ["x", "y"], "date": ["2024-01-01", "2024-01-01"],
        "applicants": ["Acme Inc", "Beta Ltd"], "inventors": ["I1", "I2"],
        "ipc": ["H01M", "H01M"],
    }))
    entity_id = store.get_all().loc[0, "applicant_entity_ids"]
    scoped = store.filtered_by_scope({"applicant_entity_ids": [entity_id]})
    assert list(scoped.get_all()["patent_number"]) == ["P1"]
