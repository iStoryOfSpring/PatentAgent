"""Pydantic 数据模型: FullPatent, Claim, Citation, PatentSummary"""

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """权利要求"""
    number: int
    text: str
    is_independent: bool
    depends_on: list[int] = Field(default_factory=list)


class Citation(BaseModel):
    """引证信息"""
    patent_number: str
    citation_type: str  # 'forward' | 'backward'
    cited_by: str | None = None
    cites: str | None = None


class FullPatent(BaseModel):
    """完整专利数据模型（Phase 3 实现全字段解析）"""
    patent_number: str
    source_record_id: str = ""
    publication_numbers: list[str] = Field(default_factory=list)
    title: str
    abstract: str
    applicants: list[str] = Field(default_factory=list)
    inventors: list[str] = Field(default_factory=list)
    ipc_codes: list[str] = Field(default_factory=list)
    cpc_codes: list[str] = Field(default_factory=list)
    publication_date: str = ""
    priority_date: str = ""
    priority_numbers: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    description: str = ""
    forward_citations: list[str] = Field(default_factory=list)
    backward_citations: list[str] = Field(default_factory=list)
    non_patent_references: list[str] = Field(default_factory=list)
    family_members: list[str] = Field(default_factory=list)
    family_details: list[str] = Field(default_factory=list)
    legal_status: str = ""
    source_file: str = ""
    imported_at: str = ""


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
