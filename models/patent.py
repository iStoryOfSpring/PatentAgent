"""Versioned canonical patent-domain models.

The flat fields remain available for the analysis tools.  New source
adapters additionally populate localized content, event history and field
provenance so that a convenient display value is never mistaken for the only
value supplied by an authority.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Party(BaseModel):
    name: str
    normalized_name: str = ""
    country: str = ""
    role: Literal["applicant", "assignee", "current_rights_holder", "inventor", "unknown"] = "unknown"
    source_role: str = ""


class Classification(BaseModel):
    scheme: Literal["IPC", "CPC", "OTHER"] = "IPC"
    code: str
    level: str = ""


class DataSource(BaseModel):
    adapter: str
    source_name: str = ""
    source_uri: str = ""
    license_note: str = ""


class RecordProvenance(BaseModel):
    source: DataSource
    source_record_id: str = ""
    source_file: str = ""
    imported_at: str = ""
    raw_record_hash: str = ""


class LocalizedText(BaseModel):
    language: str = "und"
    text: str
    truncated: bool = False


class FieldProvenance(BaseModel):
    field_name: str
    source: str
    source_record_id: str = ""
    source_path: str = ""
    observed_at: str = ""


class FieldConflict(BaseModel):
    field_name: str
    kept_value: str
    rejected_value: str
    kept_source: str
    rejected_source: str


class LegalEvent(BaseModel):
    event_code: str = ""
    description: str = ""
    event_date: str = ""
    source: str = ""
    jurisdiction: str = ""


class Claim(BaseModel):
    """权利要求"""
    number: int
    text: str
    is_independent: bool
    depends_on: list[int] = Field(default_factory=list)
    language: str = "und"
    claim_id: str = ""


class Citation(BaseModel):
    """引证信息"""
    patent_number: str
    citation_type: str  # 'forward' | 'backward'
    cited_by: str | None = None
    cites: str | None = None
    source_publication_number: str = ""
    target_publication_number: str = ""
    source: str = ""


class FullPatent(BaseModel):
    """Canonical patent record v3 with legacy flat-field compatibility."""
    schema_version: int = 3
    patent_number: str
    normalized_patent_number: str = ""
    application_number: str = ""
    source_record_id: str = ""
    publication_numbers: list[str] = Field(default_factory=list)
    title: str
    abstract: str
    language: str = "und"
    localized_titles: list[LocalizedText] = Field(default_factory=list)
    localized_abstracts: list[LocalizedText] = Field(default_factory=list)
    applicants: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    ipc_codes: list[str] = Field(default_factory=list)
    cpc_codes: list[str] = Field(default_factory=list)
    publication_date: str = ""
    filing_date: str = ""
    grant_date: str = ""
    priority_date: str = ""
    priority_numbers: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    description: str = ""
    forward_citations: list[str] = Field(default_factory=list)
    backward_citations: list[str] = Field(default_factory=list)
    non_patent_references: list[str] = Field(default_factory=list)
    family_members: list[str] = Field(default_factory=list)
    family_details: list[str] = Field(default_factory=list)
    family_id: str = ""
    legal_status: str = ""
    legal_status_as_of: str = ""
    legal_events: list[LegalEvent] = Field(default_factory=list)
    jurisdiction: str = ""
    kind_code: str = ""
    data_as_of: str = ""
    source_file: str = ""
    imported_at: str = ""
    applicant_parties: list[Party] = Field(default_factory=list)
    assignee_parties: list[Party] = Field(default_factory=list)
    current_rights_holder_parties: list[Party] = Field(default_factory=list)
    inventor_parties: list[Party] = Field(default_factory=list)
    classifications: list[Classification] = Field(default_factory=list)
    citation_records: list[Citation] = Field(default_factory=list)
    provenance: RecordProvenance | None = None
    field_provenance: list[FieldProvenance] = Field(default_factory=list)
    field_conflicts: list[FieldConflict] = Field(default_factory=list)


# New code should use PatentRecord; FullPatent remains a compatible public name.
PatentRecord = FullPatent


class FamilyInfo(BaseModel):
    """同族专利信息"""
    priority_numbers: list[str] = Field(default_factory=list)
    priority_date: str = ""
    family_members: list[str] = Field(default_factory=list)
    family_details: list[str] = Field(default_factory=list)
    designated_states: str = ""


class LegalStatus(BaseModel):
    """法律状态"""
    status: str = "unknown"
    status_date: str = ""
    source: str = ""
    note: str = ""


class PatentSummary(BaseModel):
    """检索结果轻量模型——严禁包含 claims/description/citations"""
    patent_number: str
    title: str
    abstract: str              # 截断至 500 字符
    applicants: list[str]       # 仅前 5 位
    year: int | None = None
    ipc_sections: list[str] = Field(default_factory=list)  # 部级分类，如 ["H01M", "H02J"]
    relevance_score: float = 0.0
