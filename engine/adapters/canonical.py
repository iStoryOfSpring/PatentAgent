"""Replayable canonical publication JSONL; no inference of unavailable fields."""
import json
from engine.adapters.base import PatentAdapter
from models.patent import PatentRecord

class CanonicalJsonlAdapter(PatentAdapter):
    name = "canonical"
    display_name = "PatentAgent canonical v4 JSONL"
    version = "4.0"

    def detect(self, filepath):
        if not filepath.endswith((".jsonl", ".ndjson")): return False
        try:
            with open(filepath, encoding="utf-8") as handle:
                item = json.loads(next(line for line in handle if line.strip()))
            return item.get("schema_version") == 4 and "patent_number" in item
        except (ValueError, OSError, StopIteration, AttributeError): return False

    def parse_file(self, filepath):
        self._reset_parse_diagnostics()
        records = []
        with open(filepath, encoding="utf-8") as handle:
            for index, line in enumerate(handle, 1):
                if not line.strip(): continue
                self.parse_diagnostics["expected"] += 1
                self.parse_diagnostics["detected"] += 1
                try:
                    payload = json.loads(line)
                    if payload.get("schema_version") != 4:
                        raise ValueError("canonical schema_version must be 4")
                    record = PatentRecord.model_validate(payload)
                    from engine.adapters.common import normalized_document_number
                    identity = normalized_document_number(record.patent_number)
                    if record.record_type != "publication" or not identity or not record.normalized_patent_number or record.normalized_patent_number != identity:
                        raise ValueError("canonical publication identity mismatch")
                    records.append(record)
                    self.parse_diagnostics["succeeded"] += 1
                except ValueError:
                    self._record_parse_issue(filepath=filepath,record_id=str(index),location=f"line:{index}",code="canonical_invalid",message="Invalid canonical record",sample=line)
        return records
