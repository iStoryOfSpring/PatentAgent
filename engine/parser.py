"""专利数据解析引擎 — 从 PatentSmelter 迁移, Phase 3 扩展全字段解析

WoS Derwent 数据实际可用字段:
  PN, TI, AE, AU, AB, IP, DC, PD, PI, CR, FD, DS, GA, UT
不可用字段（WoS 不含全文）:
  CL (权利要求) — 需全文专利源(CNKI/Google Patents/PatentSoul)
  说明书正文 — 同上
  法律状态 — 需法律状态数据库
"""

import hashlib
import os
import pickle
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import pandas as pd

from models.patent import (
    FullPatent, Claim, Citation, FamilyInfo, LegalStatus, PatentSummary,
)

PARSER_CACHE_VERSION = "4.1"

# ── WoS 字段正则（复用 + 新增） ──
_RE_PN = re.compile(r'^PN\s+(.+)$', re.M)
_RE_TI = re.compile(r'^TI\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_AE = re.compile(r'^AE\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_AU = re.compile(r'^AU\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_AB = re.compile(r'^AB\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_IP = re.compile(r'^IP\s+(.+)$', re.M)
_RE_DC = re.compile(r'^DC\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_PD = re.compile(r'^PD\s+\S+\s+(\d{2}\s[A-Z][a-z]{2}\s\d{4})', re.M)
_RE_PI = re.compile(r'^PI\s+(.+)$', re.M)
_RE_CR = re.compile(r'^CR\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_CP = re.compile(r'^CP\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_FD = re.compile(r'^FD\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_DS = re.compile(r'^DS\s+(.*?)(?=\n[A-Z]{2}\s|$)', re.S | re.M)
_RE_UT = re.compile(r'^UT\s+(.+)$', re.M)

# 申请人/发明人每行提取
_RE_ENTITY_LINE = re.compile(r'^(.*?)(?:\s\(|$)', re.M)

# PI 日期提取
_RE_PI_DATE = re.compile(r'(\d{2}\s[A-Z][a-z]{2}\s\d{4})')

# 公开号提取（Derwent PN/CP/PI/FD/DS）
_RE_CR_PN = re.compile(r'([A-Z]{2}\d{6,}[A-Z0-9-]*)', re.M)


class PatentMiner:
    """WoS 格式专利文本解析器

    Phase 1: parse_txt(), batch_process() — 基本不动
    Phase 3: parse_full_record(), parse_claims(), parse_citations(),
             parse_family_info(), parse_legal_status() — 新增
    """

    def __init__(self, input_dir: str,
                 stopwords_path: Optional[str] = None,
                 entity_map: Optional[dict[str, str]] = None) -> None:
        self.input_dir = input_dir
        self.stopwords: set[str] = set()
        if stopwords_path and os.path.exists(stopwords_path):
            with open(stopwords_path, 'r', encoding='utf-8') as f:
                self.stopwords = {line.strip() for line in f if line.strip()}
        self.entity_map: dict[str, str] = entity_map or {}

    def _clean_entity(self, name: str) -> str:
        name = name.strip()
        return self.entity_map.get(name, name)

    def _extract_entities(self, record: str, tag: str) -> list[str]:
        """从多行实体字段提取名称列表（用于 AE, AU 等）"""
        regex = re.compile(
            rf'^{tag}\s+(.*?)(?=\n[A-Z]{{2}}\s|$)', re.S | re.M,
        )
        m = regex.search(record)
        if not m:
            return []
        names = _RE_ENTITY_LINE.findall(m.group(1))
        return [self._clean_entity(n) for n in names if n.strip()]

    def _extract_field(self, record: str, pattern: 're.Pattern') -> str:
        """提取单行字段值"""
        m = pattern.search(record)
        return m.group(1).replace('\n', ' ').strip() if m else ""

    def _extract_multiline(self, record: str, pattern: 're.Pattern') -> str:
        """提取多行字段值。

        WoS 多行字段格式: 首行 = TAG value，续行 = 缩进空白 + 延续内容。
        新字段标记 = 行首为 [A-Z]{2} （两个大写字母后跟空格）。

        用贪心匹配首行 + 所有缩进续行，到下一个 field tag 或记录末尾停止。
        """
        m = pattern.search(record)
        if not m:
            return ""
        first_line = m.group(1)

        # 从匹配结束位置继续，收集缩进续行(不以 [A-Z]{2} 开头)
        rest_start = m.end()
        remaining = record[rest_start:]
        continuation = []
        for line in remaining.split('\n'):
            if re.match(r'^[A-Z]{2}\s', line):
                break
            if line.strip():
                continuation.append(line.strip())
            elif continuation:
                break  # 空行则停止续行收集

        full_text = first_line
        if continuation:
            full_text += '\n' + '\n'.join(continuation)
        return full_text.replace('\n', ' ').strip()

    # ── Phase 1: 基本解析（向后兼容） ──
    def parse_txt(self, filepath: str) -> pd.DataFrame:
        """解析 WoS 文件为 DataFrame。Phase 3 增强: 新增 inventors, priority_info,
        derwent_classes, cited_refs, family_details 列。
        v2.1: 直接在解析时计算 year 列，避免 prepare_patent_df 重解析日期。"""
        fname = os.path.basename(filepath)
        patents = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                records = content.split('\nER\n')

                for record in records:
                    if (not record.strip() or record.startswith('FN ') or
                            not _RE_PN.search(record)):
                        continue

                    data = self._record_to_dict(record)
                    data['source_file'] = fname
                    # 从 publication_date 直接提取年份
                    pub_date = data.get('publication_date', '')
                    data['year'] = int(pub_date[:4]) if pub_date and len(pub_date) >= 4 else None
                    # Phase 1 兼容: 列表/对象字段序列化为字符串
                    data['applicants'] = ';'.join(data.get('applicants', []))
                    data['inventors'] = ';'.join(data.get('inventors', []))
                    data['derwent_classes'] = ';'.join(data.get('derwent_classes', []))
                    data['cited_refs'] = ';'.join(data.get('cited_refs', []))
                    data['backward_citations'] = data['cited_refs']
                    data['family_details'] = ';'.join(data.get('family_details', []))
                    data['family_members'] = ';'.join(data.get('family_members', []))
                    data['publication_numbers'] = ';'.join(data.get('publication_numbers', []))
                    data['priority_numbers'] = ';'.join(data.get('priority_numbers', []))
                    data['non_patent_references'] = '\n'.join(
                        data.get('non_patent_references', [])
                    )
                    patents.append(data)

        except Exception as e:
            logging.error(f"解析文件 {filepath} 失败: {str(e)}")

        return pd.DataFrame(patents)

    def _record_to_dict(self, record: str) -> dict:
        """将单条专利记录解析为字段字典（所有字段为 Python 原生类型）"""
        # ── 基本字段 ──
        pn_raw = self._extract_field(record, _RE_PN)
        publication_numbers = [
            value.strip() for value in pn_raw.split(';') if value.strip()
        ]
        pn = publication_numbers[0] if publication_numbers else ""
        source_record_id = self._extract_field(record, _RE_UT)
        title = self._extract_multiline(record, _RE_TI)
        abstract = self._extract_multiline(record, _RE_AB)
        applicants = self._extract_entities(record, 'AE')

        # ── 日期 ──
        pd_match = _RE_PD.search(record)
        pub_date = ""
        if pd_match:
            try:
                pub_date = datetime.strptime(
                    pd_match.group(1), '%d %b %Y',
                ).strftime('%Y-%m-%d')
            except Exception:
                pub_date = ""

        # ── 分类 ──
        ipc_raw = self._extract_field(record, _RE_IP)
        ipc_codes = [c.strip() for c in ipc_raw.split(';') if c.strip()]

        dc_raw = self._extract_multiline(record, _RE_DC)
        derwent_classes = []
        for part in dc_raw.split(';'):
            code = part.strip().split(' ')[0] if part.strip() else ''
            if code and code[0].isalpha():
                derwent_classes.append(code)

        # ── Phase 3 新增: 发明人 ──
        inventors = self._extract_entities(record, 'AU')

        # ── Phase 3 新增: 优先权信息 ──
        pi_raw = self._extract_field(record, _RE_PI)
        priority_date = ""
        priority_numbers = []
        if pi_raw:
            date_m = _RE_PI_DATE.search(pi_raw)
            if date_m:
                try:
                    priority_date = datetime.strptime(
                        date_m.group(1), '%d %b %Y',
                    ).strftime('%Y-%m-%d')
                except (TypeError, ValueError) as exc:
                    logging.warning("无法解析优先权日期 %r: %s", date_m.group(1), exc)
            # 优先权号
            for token in pi_raw.split():
                if re.match(r'^[A-Z]{2}\d+', token):
                    priority_numbers.append(token)

        # ── 引证信息 ──
        # Derwent 的 CP 才是 cited patents；CR 保存非专利参考文献。
        # CP 常把当前记录的公开号列在首位，因此必须排除全部 PN 成员，避免自环。
        cp_raw = self._extract_multiline(record, _RE_CP)
        own_numbers = {value.upper() for value in publication_numbers}
        cited_refs = [
            value for value in _RE_CR_PN.findall(cp_raw or "")
            if value.upper() not in own_numbers
        ]
        cited_refs = list(dict.fromkeys(cited_refs))
        cr_raw = self._extract_multiline(record, _RE_CR)
        non_patent_references = [
            item.strip() for item in re.split(r';\s*', cr_raw) if item.strip()
        ]

        # ── Phase 3 新增: 同族/关联申请 ──
        fd_raw = self._extract_multiline(record, _RE_FD)
        family_details = []
        if fd_raw:
            family_details = [f.strip() for f in fd_raw.split('\n') if f.strip()]

        # PN 的其余公开号与 FD previous publication 是可验证的同族/关联公开号。
        # PI 是优先权申请号，DS 是指定国，不应膨胀为同族成员。
        ds_raw = self._extract_multiline(record, _RE_DS)
        family_members = publication_numbers[1:]
        for text in [fd_raw]:
            if text:
                family_members.extend(
                    value for value in _RE_CR_PN.findall(text) if '-' in value
                )
        family_members = [
            value for value in dict.fromkeys(family_members)
            if value.upper() != pn.upper()
        ]

        return {
            'patent_number': pn or "Unknown",
            'source_record_id': source_record_id,
            'title': title,
            'abstract': abstract,
            'applicants': applicants,
            'inventors': inventors,
            'ipc': ipc_raw,
            'ipc_codes': ipc_codes,
            'derwent_classes': derwent_classes,
            'date': pub_date,              # 向后兼容: 旧代码用 date
            'publication_date': pub_date,  # 新代码用 publication_date
            'priority_date': priority_date,
            'priority_numbers': priority_numbers,
            'cited_refs': cited_refs,
            'non_patent_references': non_patent_references,
            'publication_numbers': publication_numbers,
            'family_members': family_members,
            'family_details': family_details,
            'designated_states': self._extract_multiline(record, _RE_DS),
            'source_file': '',
            'record_raw': record,
        }

    # ── 缓存 (Parquet 格式) ──
    def _cache_path(self) -> str:
        return os.path.join(self.input_dir, ".patent_cache.parquet")

    def _hash_path(self) -> str:
        return os.path.join(self.input_dir, ".patent_cache.hash")

    def _files_hash(self, files: list[str]) -> str:
        """计算所有文件的哈希，用于检测文件变更"""
        h = hashlib.sha256()
        h.update(PARSER_CACHE_VERSION.encode())
        for f in sorted(files):
            fpath = os.path.join(self.input_dir, f)
            h.update(f.encode())
            h.update(str(os.path.getmtime(fpath)).encode())
        return h.hexdigest()[:16]

    def _load_cache(self) -> pd.DataFrame | None:
        cache_path = self._cache_path()
        hash_path = self._hash_path()
        if not os.path.exists(cache_path):
            return None
        files = [f for f in os.listdir(self.input_dir) if f.lower().endswith('.txt')]
        if not files:
            return None
        current_hash = self._files_hash(files)
        try:
            # Read hash separately — fast, no need to open the parquet
            if os.path.exists(hash_path):
                with open(hash_path, 'r') as f:
                    cached_hash = f.read().strip()
                if cached_hash != current_hash:
                    return None

            # Parquet: columnar format, only reads metadata + selected columns
            df = pd.read_parquet(cache_path)
            if not df.empty:
                return df
        except Exception as exc:
            logging.warning("读取解析缓存失败，将重建缓存: %s", exc)
        return None

    def _save_cache(self, df: pd.DataFrame) -> None:
        files = [f for f in os.listdir(self.input_dir) if f.lower().endswith('.txt')]
        current_hash = self._files_hash(files)
        try:
            # Write hash file
            with open(self._hash_path(), 'w') as f:
                f.write(current_hash)
            # Write parquet (Snappy-compressed columnar storage)
            df.to_parquet(self._cache_path(), compression='snappy', index=False)
        except Exception as exc:
            logging.warning("写入解析缓存失败: %s", exc)

    def batch_process(self) -> pd.DataFrame:
        """批量解析目录下所有 .txt 文件（并行 + Pickle 缓存）"""
        if not os.path.exists(self.input_dir):
            print(f"错误: 找不到目录 '{self.input_dir}'")
            return pd.DataFrame()

        files = [f for f in os.listdir(self.input_dir) if f.lower().endswith('.txt')]
        if not files:
            return pd.DataFrame()

        # ── 尝试读缓存 ──
        cached = self._load_cache()
        if cached is not None:
            print(f"从缓存加载 {len(cached):,} 条专利（{len(files)} 个文件未变化）")
            return cached

        # ── 并行解析 ──
        print(f"正在并行解析 {len(files)} 个文件...")
        all_data = []
        with ThreadPoolExecutor(max_workers=min(8, len(files))) as executor:
            futures = {
                executor.submit(self.parse_txt, os.path.join(self.input_dir, fn)): fn
                for fn in files
            }
            for future in as_completed(futures):
                df = future.result()
                if not df.empty:
                    all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)

        # ── 写缓存 ──
        self._save_cache(result)
        print(f"解析完成: {len(result):,} 条专利，缓存已保存")

        return result

    def batch_process_full(self) -> list[FullPatent]:
        """批量解析，返回 FullPatent 列表（并行）"""
        results = []
        if not os.path.exists(self.input_dir):
            return results

        files = [f for f in os.listdir(self.input_dir)
                 if f.lower().endswith('.txt')]

        print(f"正在并行解析 {len(files)} 个文件为 FullPatent ...")
        with ThreadPoolExecutor(max_workers=min(8, len(files))) as executor:
            futures = {
                executor.submit(self.parse_file_to_full,
                                os.path.join(self.input_dir, fn)): fn
                for fn in files
            }
            for future in as_completed(futures):
                results.extend(future.result())

        return results

    def parse_file_to_full(self, filepath: str) -> list[FullPatent]:
        """解析单个文件，返回 FullPatent 列表"""
        results = []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                records = content.split('\nER\n')

                for record in records:
                    if (not record.strip() or record.startswith('FN ') or
                            not _RE_PN.search(record)):
                        continue
                    fp = self.parse_full_record(record)
                    fp.source_file = os.path.basename(filepath)
                    fp.imported_at = datetime.now().isoformat()
                    results.append(fp)

        except Exception as e:
            logging.error(f"解析文件 {filepath} 失败: {str(e)}")

        return results

    # ── Phase 3: 全字段解析方法 ──
    def parse_full_record(self, record_text: str) -> FullPatent:
        """解析完整专利记录 → FullPatent Pydantic 模型

        WoS Derwent 数据源限制:
          - claims: 不含（需全文数据源）
          - description: 不含（需全文数据源）
          - cpc_codes: 不含（Derwent 使用自有 DC 分类，非 CPC）
          - forward_citations: 不含（需 cited-by 数据）
          - legal_status: 不含（需法律状态数据库）
        """
        d = self._record_to_dict(record_text)
        return FullPatent(
            patent_number=d['patent_number'],
            source_record_id=d['source_record_id'],
            publication_numbers=d['publication_numbers'],
            title=d['title'],
            abstract=d['abstract'],
            applicants=d['applicants'],
            inventors=d['inventors'],
            ipc_codes=d['ipc_codes'],
            cpc_codes=[],       # WoS Derwent 不含 CPC，DC 分类另存
            publication_date=d['publication_date'],
            priority_date=d['priority_date'],
            priority_numbers=d['priority_numbers'],
            claims=[],          # WoS Derwent 不含权利要求全文（需全文数据源）
            description="",     # WoS Derwent 不含说明书正文
            forward_citations=[],  # WoS 不含被引信息
            backward_citations=d['cited_refs'],
            non_patent_references=d['non_patent_references'],
            family_members=d['family_members'],
            family_details=d['family_details'],
            legal_status="",    # WoS Derwent 不含法律状态
            source_file="",
            imported_at="",
        )

    def parse_claims(self, record_text: str) -> list[Claim]:
        """解析权利要求，区分独立和从属权利要求。

        注意: WoS Derwent 导出不含权利要求(CL字段)。
        需要 CNKI、Google Patents、PatentSoul 或各国专利局全文数据源。
        此处返回空列表，待后续接入全文数据源后实现。
        """
        # 尝试 CL 字段（WoS 通常不包含）
        cl_match = re.search(
            r'^CL\s+(.*?)(?=\n[A-Z]{2}\s|$)', record_text, re.S | re.M,
        )
        if not cl_match:
            return []

        claims_text = cl_match.group(1)
        claims = []
        # 解析编号的权利要求
        claim_pattern = re.compile(r'(\d+)\.\s+(.*?)(?=\n\d+\.\s|\Z)', re.S)
        for m in claim_pattern.finditer(claims_text):
            num = int(m.group(1))
            text = m.group(2).replace('\n', ' ').strip()
            is_independent = (num == 1)  # Claim 1 通常为独立权利要求
            claims.append(Claim(
                number=num,
                text=text[:2000],
                is_independent=is_independent,
                depends_on=[] if is_independent else [num - 1],
            ))
        return claims

    def parse_citations(self, record_text: str) -> list[Citation]:
        """解析引证信息，区分前引(backward)和后引(forward)。

        WoS Derwent CP 字段 = 该专利引用的其他专利（backward citations）；
        CR 是非专利参考文献，不进入专利引证图。
        Forward citations 需额外数据源（如 Google Patents cited-by）。
        """
        citations = []
        d = self._record_to_dict(record_text)
        for pn in d['cited_refs']:
            citations.append(Citation(
                patent_number=pn,
                citation_type='backward',  # 该专利引用了 pn
                cited_by=None,
                cites=pn,
            ))
        return citations

    def parse_family_info(self, record_text: str) -> FamilyInfo:
        """解析同族专利信息 → FamilyInfo Pydantic 模型"""
        d = self._record_to_dict(record_text)
        return FamilyInfo(
            priority_numbers=d['priority_numbers'],
            priority_date=d['priority_date'],
            family_members=d['family_members'],
            family_details=d['family_details'],
            designated_states=d['designated_states'],
        )

    def parse_legal_status(self, record_text: str) -> LegalStatus:
        """解析法律状态 → LegalStatus Pydantic 模型。

        注意: WoS Derwent 导出不含法律状态信息。
        需各国专利局法律状态数据库或商业数据源。
        """
        return LegalStatus(
            status='unknown',
            status_date='',
            source='not_available_in_wos_derwent',
            note='法律状态需专利局数据库或商业数据源（如 INPADOC）',
        )
