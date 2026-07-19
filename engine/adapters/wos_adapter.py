"""WoS Derwent adapter — wraps existing PatentMiner parse logic."""

import os

from engine.adapters.base import PatentAdapter
from engine.parser import PatentMiner
from models.patent import FullPatent


class WoSAdapter(PatentAdapter):
    name = "wos"
    display_name = "Web of Science Derwent"
    # 3.0: PN 多公开号、CP 专利引证、CR 非专利文献与日期别名修正。
    version = "4.1"

    def detect(self, filepath: str) -> bool:
        if not filepath.lower().endswith('.txt'):
            return False
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                head = f.read(200)
            return 'FN Clarivate' in head or 'FN Thomson Reuters' in head
        except Exception:
            return False

    def parse_file(self, filepath: str) -> list[FullPatent]:
        miner = PatentMiner(input_dir=os.path.dirname(filepath))
        # Use existing parse_txt which returns DataFrame
        df = miner.parse_txt(filepath)
        if df.empty:
            return []
        # Convert DataFrame rows to FullPatent
        patents = []
        for _, row in df.iterrows():
            fp = FullPatent(
                patent_number=str(row.get('patent_number', '')),
                source_record_id=str(row.get('source_record_id', '')),
                publication_numbers=_split(row.get('publication_numbers', '')),
                title=str(row.get('title', '')),
                abstract=str(row.get('abstract', '')),
                applicants=_split(row.get('applicants', '')),
                inventors=_split(row.get('inventors', '')),
                ipc_codes=_split(row.get('ipc', '')),
                cpc_codes=[],
                publication_date=str(row.get('publication_date', '')),
                priority_date=str(row.get('priority_date', '')),
                priority_numbers=_split(row.get('priority_numbers', '')),
                claims=[],
                description='',
                forward_citations=[],
                backward_citations=_split(row.get('cited_refs', '')),
                non_patent_references=_split_lines(row.get('non_patent_references', '')),
                family_members=_split(row.get('family_members', '')),
                family_details=_split(row.get('family_details', '')),
                legal_status='',
                source_file=os.path.basename(filepath),
                imported_at='',
            )
            patents.append(fp)
        return patents


def _split(val) -> list[str]:
    if not val or not isinstance(val, str):
        return []
    return [s.strip() for s in val.split(';') if s.strip()]


def _split_lines(val) -> list[str]:
    if not val or not isinstance(val, str):
        return []
    return [s.strip() for s in val.splitlines() if s.strip()]
