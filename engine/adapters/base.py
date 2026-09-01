"""Patent data source adapter base class.

Each data source (WoS, PatentSoul, Google Patents, CNKI, etc.) implements
a PatentAdapter subclass. The adapter's job is to parse raw files into a
list of FullPatent Pydantic models. Everything downstream (DataStore, Tools,
Agent) works with FullPatent and never sees the raw format.
"""

import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd

from models.patent import FullPatent

logger = logging.getLogger(__name__)


class PatentAdapter(ABC):
    """Parse raw patent data files into FullPatent objects.

    Subclasses must implement:
      - name / display_name: human-readable identifiers
      - detect(filepath) → bool: can this adapter handle this file?
      - parse_file(filepath) → list[FullPatent]: parse one file

    The base class provides:
      - batch_parse(input_dir) → pd.DataFrame: file discovery, parallel parsing, caching
      - available_fields → set[str]: which FullPatent fields this adapter fills
    """

    name: str = ""
    display_name: str = ""
    version: str = "1.0"

    def _reset_parse_diagnostics(self) -> None:
        self.parse_diagnostics = {
            "expected": 0,
            "detected": 0,
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "issues": [],
        }

    def _record_parse_issue(
        self, *, filepath: str, record_id: str, location: str,
        code: str, message: str, sample: str | bytes = "",
        outcome: str = "failed",
    ) -> None:
        if not hasattr(self, "parse_diagnostics"):
            self._reset_parse_diagnostics()
        sample_bytes = sample if isinstance(sample, bytes) else str(sample).encode("utf-8")
        self.parse_diagnostics[outcome] += 1
        self.parse_diagnostics["issues"].append({
            "file": os.path.basename(filepath),
            "record_id": record_id,
            "location": location,
            "code": code,
            "message": message,
            "sample_hash": hashlib.sha256(sample_bytes).hexdigest() if sample_bytes else "",
        })

    # ── Abstract ──

    @abstractmethod
    def detect(self, filepath: str) -> bool:
        """Return True if this adapter can parse the given file."""
        ...

    @abstractmethod
    def parse_file(self, filepath: str) -> list[FullPatent]:
        """Parse a single file into FullPatent objects."""
        ...

    # ── Shared batch logic ──

    def batch_parse(self, input_dir: str,
                    max_workers: int = 8) -> pd.DataFrame:
        """File discovery → parallel parse → concat → Parquet cache → DataFrame.

        Returns a DataFrame with all FullPatent fields as columns.
        """
        if not os.path.isdir(input_dir):
            logger.warning("Input directory not found: %s", input_dir)
            return pd.DataFrame()

        files = self._discover_files(input_dir)
        if not files:
            logger.warning("No parseable files found in %s", input_dir)
            return pd.DataFrame()

        # Try cache
        cached = self._load_cache(input_dir, files)
        if cached is not None:
            logger.info("[%s] Cache hit: %d patents", self.name, len(cached))
            return cached

        # Parallel parse
        logger.info("[%s] Parsing %d files...", self.name, len(files))
        all_patents: list[FullPatent] = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(files))) as pool:
            futures = {
                pool.submit(self._parse_file_safe, os.path.join(input_dir, fn)): fn
                for fn in files
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    all_patents.extend(result)

        if not all_patents:
            return pd.DataFrame()

        df = self._patents_to_dataframe(all_patents)
        # DII exports can overlap across batches. UT is the authoritative record
        # identifier; fall back to the primary publication number when UT is absent.
        if 'source_record_id' in df.columns:
            dedupe_key = df['source_record_id'].where(
                df['source_record_id'].astype(str).str.strip().ne(''),
                df['patent_number'],
            )
            df = df.loc[~dedupe_key.duplicated(keep='first')].reset_index(drop=True)
        self._save_cache(input_dir, files, df)
        logger.info("[%s] Parsed %d patents, cache saved", self.name, len(df))
        return df

    def _discover_files(self, input_dir: str) -> list[str]:
        """Find files this adapter can handle."""
        return sorted(
            f for f in os.listdir(input_dir)
            if self.detect(os.path.join(input_dir, f))
        )

    def _parse_file_safe(self, filepath: str) -> list[FullPatent] | None:
        try:
            return self.parse_file(filepath)
        except Exception as e:
            logger.error("[%s] Failed to parse %s: %s", self.name, filepath, e)
            return None

    # ── Cache (Parquet) ──

    def _cache_path(self, input_dir: str) -> str:
        return os.path.join(input_dir, f".patent_cache_{self.name}.parquet")

    def _hash_path(self, input_dir: str) -> str:
        return os.path.join(input_dir, f".patent_cache_{self.name}.hash")

    def _files_hash(self, input_dir: str, files: list[str]) -> str:
        h = hashlib.sha256()
        h.update(self.version.encode())
        for f in sorted(files):
            fpath = os.path.join(input_dir, f)
            h.update(f.encode())
            with open(fpath, "rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    h.update(chunk)
        return h.hexdigest()[:16]

    def _load_cache(self, input_dir: str,
                    files: list[str]) -> Optional[pd.DataFrame]:
        cache_path = self._cache_path(input_dir)
        hash_path = self._hash_path(input_dir)
        if not os.path.exists(cache_path):
            return None
        current_hash = self._files_hash(input_dir, files)
        try:
            if os.path.exists(hash_path):
                with open(hash_path, 'r') as f:
                    if f.read().strip() != current_hash:
                        return None
            return pd.read_parquet(cache_path)
        except Exception:
            return None

    def _save_cache(self, input_dir: str, files: list[str],
                    df: pd.DataFrame) -> None:
        try:
            with open(self._hash_path(input_dir), 'w') as f:
                f.write(self._files_hash(input_dir, files))
            df.to_parquet(self._cache_path(input_dir),
                          compression='snappy', index=False)
        except Exception as e:
            logger.warning("[%s] Failed to write cache: %s", self.name, e)

    # ── DataFrame conversion ──

    @staticmethod
    def _patents_to_dataframe(patents: list[FullPatent]) -> pd.DataFrame:
        """Convert FullPatent list to DataFrame with flat columns."""
        rows = []
        for p in patents:
            rows.append({
                'patent_number': p.patent_number,
                'normalized_patent_number': p.normalized_patent_number,
                'application_number': p.application_number,
                'source_record_id': p.source_record_id,
                'publication_numbers': ';'.join(p.publication_numbers),
                'title': p.title,
                'abstract': p.abstract,
                'language': p.language,
                'localized_titles_json': _json_dump(p.localized_titles),
                'localized_abstracts_json': _json_dump(p.localized_abstracts),
                'applicants': ';'.join(p.applicants),
                'inventors': ';'.join(p.inventors),
                'ipc_codes_str': ';'.join(p.ipc_codes),
                'cpc_codes': ';'.join(p.cpc_codes) if p.cpc_codes else '',
                'publication_date': p.publication_date,
                'filing_date': p.filing_date,
                'grant_date': p.grant_date,
                'priority_date': p.priority_date,
                'priority_numbers': ';'.join(p.priority_numbers),
                'claims_json': _serialize_claims(p.claims),
                'description': p.description,
                'forward_citations': ';'.join(p.forward_citations),
                'backward_citations': ';'.join(p.backward_citations),
                'non_patent_references': '\n'.join(p.non_patent_references),
                'family_members': ';'.join(p.family_members),
                'family_details': ';'.join(p.family_details),
                'family_id': p.family_id,
                'legal_status': p.legal_status,
                'legal_status_as_of': p.legal_status_as_of,
                'legal_events_json': _json_dump(p.legal_events),
                'jurisdiction': p.jurisdiction,
                'kind_code': p.kind_code,
                'data_as_of': p.data_as_of,
                'field_provenance_json': _json_dump(p.field_provenance),
                'field_conflicts_json': _json_dump(p.field_conflicts),
                'record_provenance_json': (
                    p.provenance.model_dump_json() if p.provenance else ''
                ),
                'applicant_parties_json': _json_dump(p.applicant_parties),
                'assignee_parties_json': _json_dump(p.assignee_parties),
                'current_rights_holder_parties_json': _json_dump(p.current_rights_holder_parties),
                'inventor_parties_json': _json_dump(p.inventor_parties),
                'source_file': p.source_file,
            })
        df = pd.DataFrame(rows)
        # Derive year/month/country columns
        if 'publication_date' in df.columns and not df.empty:
            dates = pd.to_datetime(df['publication_date'], errors='coerce')
            df['year'] = dates.dt.year
            df['month'] = dates.dt.month.fillna(1).astype(int)
            df['date'] = df['publication_date']  # backward compat alias
            df['country'] = (
                df['patent_number'].astype(str)
                .str.extract(r'^([A-Za-z]{2})')[0]
                .fillna('Unknown').str.upper()
            )
        # Backward compat aliases
        if 'ipc_codes_str' in df.columns:
            df['ipc'] = df['ipc_codes_str']
        if 'publication_date' in df.columns:
            df['date'] = df['publication_date']
        return df


def _serialize_claims(claims: list) -> str:
    if not claims:
        return ''
    import json
    return json.dumps([
        claim.model_dump(mode="json") if hasattr(claim, "model_dump") else claim
        for claim in claims
    ], ensure_ascii=False, separators=(",", ":"))


def _json_dump(values: list) -> str:
    import json
    return json.dumps([
        value.model_dump(mode="json") if hasattr(value, "model_dump") else value
        for value in values
    ], ensure_ascii=False, separators=(",", ":"))
