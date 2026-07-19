"""PatentRepository — SQLite + ChromaDB 双库管理"""

import pandas as pd
from models.patent import FullPatent, PatentSummary


class DatasetSummary:
    total_patents: int
    year_range: tuple[int, int]
    ipc_sections: list[str]
    top_applicants: list[tuple[str, int]]


class PatentFilter:
    year_start: int | None = None
    year_end: int | None = None
    ipc_codes: list[str] | None = None
    applicant: str | None = None


class PatentRepository:
    """专利数据仓库。SQLite（主源）+ ChromaDB（向量索引）。

    双库一致性:
      - SQLite source of truth, ChromaDB 派生索引
      - WAL 模式 + aiosqlite 支持并发写
      - 软删除 → 同步更新 ChromaDB metadata.is_deleted
      - 查询阶段用 where={"is_deleted": False} 过滤，保证 Top-K 语义
      - 每次数据变更后自动调用 cache.invalidate(dataset_id)
    """

    def __init__(self, db_path: str, vector_store=None): ...
    def _init_db(self):
        """PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"""
        ...

    # ── 写入（事务保证 + 缓存失效） ──
    def import_from_wos_txt(self, filepath: str) -> int:
        """WoS txt → SQLite → ChromaDB → cache.invalidate()"""
        ...

    def add_patents(self, patents: list[FullPatent]): ...
    def update_patent(self, patent: FullPatent): ...
    def delete_patent(self, patent_number: str):
        """软删除: SQLite deleted_at + ChromaDB is_deleted=True + cache.invalidate()"""
        ...

    def rebuild_vector_index(self) -> int:
        """从 SQLite 全量重建 ChromaDB（修复/模型切换时调用）"""
        ...

    def verify_consistency(self) -> dict:
        """检查 SQLite ↔ ChromaDB 记录数，返回差异报告"""
        ...

    # ── 查询 ──
    def get_patent(self, patent_number: str) -> FullPatent | None: ...
    def query_patents(self, filters: PatentFilter) -> pd.DataFrame: ...
    def get_all_patents(self, active_only: bool = True) -> pd.DataFrame: ...
    def get_patents_by_year_range(self, start: int, end: int) -> pd.DataFrame: ...
    def get_patents_by_ipc(self, ipc_codes: list[str]) -> pd.DataFrame: ...
    def get_patents_by_applicant(self, name: str) -> pd.DataFrame: ...
    def search_patents(self, query: str) -> list[PatentSummary]: ...
    def export_csv(self, filepath: str) -> str: ...

    # ── 元数据 ──
    def get_dataset_summary(self) -> DatasetSummary: ...
    def get_available_years(self) -> list[int]: ...
    def get_available_ipc_sections(self) -> list[str]: ...
    def get_applicant_list(self) -> list[str]: ...
