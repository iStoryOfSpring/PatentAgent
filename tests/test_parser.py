"""测试: engine/parser.py — PatentMiner"""

import os
import tempfile

import pandas as pd
import pytest

from engine.parser import PatentMiner


# 模拟真实 WoS 导出格式: FN 记录仅在文件头出现一次，后面全是真实专利
SAMPLE_RECORD = """FN Clarivate Analytics Web of Science
VR 1.0
ER

PN CN123456789A
TI 一种高效的锂电池正极材料及其制备方法
AE 宁德时代新能源科技股份有限公司 (Firm)
PD 2024-03-15 15 Mar 2024
AB 本发明公开了一种锂电池正极材料，具有高能量密度和优异的循环稳定性。
IP H01M-004/58; C01B-025/45
ER

PN US20240001234A1
TI Solid state battery electrolyte composition
AE Toyota Motor Corp (Corp)
   Panasonic Corp (Corp)
PD 2024-01-10 10 Jan 2024
AB A solid electrolyte composition comprising sulfide-based materials.
IP H01M-010/056; H01M-010/0525
ER
"""


@pytest.fixture
def temp_input_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_patents.txt")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(SAMPLE_RECORD)
        yield tmpdir


class TestPatentMiner:
    def test_parse_txt_normal(self, temp_input_dir):
        """正常输入: 解析两条专利记录"""
        miner = PatentMiner(input_dir=temp_input_dir)
        filepath = os.path.join(temp_input_dir, "test_patents.txt")
        df = miner.parse_txt(filepath)
        assert len(df) == 2
        assert df.iloc[0]['patent_number'] == 'CN123456789A'
        assert '锂电池' in df.iloc[0]['title']
        assert df.iloc[0]['applicants'] == '宁德时代新能源科技股份有限公司'
        assert df.iloc[0]['date'] == '2024-03-15'
        assert 'H01M' in df.iloc[0]['ipc']

    def test_parse_txt_english(self, temp_input_dir):
        """英文专利解析"""
        miner = PatentMiner(input_dir=temp_input_dir)
        filepath = os.path.join(temp_input_dir, "test_patents.txt")
        df = miner.parse_txt(filepath)
        assert df.iloc[1]['patent_number'] == 'US20240001234A1'
        assert 'Solid state' in df.iloc[1]['title']
        assert 'Toyota Motor Corp' in df.iloc[1]['applicants']

    def test_parse_txt_empty_file(self, temp_input_dir):
        """空输入: 空文件"""
        empty_path = os.path.join(temp_input_dir, "empty.txt")
        with open(empty_path, 'w', encoding='utf-8') as f:
            f.write("FN 0\nER\n")
        miner = PatentMiner(input_dir=temp_input_dir)
        df = miner.parse_txt(empty_path)
        assert len(df) == 0

    def test_parse_txt_missing_fields(self, temp_input_dir):
        """缺失字段: 只有 patent_number"""
        minimal_path = os.path.join(temp_input_dir, "minimal.txt")
        with open(minimal_path, 'w', encoding='utf-8') as f:
            f.write("PN CN000000A\nER\n")
        miner = PatentMiner(input_dir=temp_input_dir)
        df = miner.parse_txt(minimal_path)
        assert len(df) == 1
        assert df.iloc[0]['patent_number'] == 'CN000000A'
        assert df.iloc[0]['title'] == ''

    def test_batch_process(self, temp_input_dir):
        """批量处理"""
        miner = PatentMiner(input_dir=temp_input_dir)
        df = miner.batch_process()
        assert len(df) == 2

    def test_batch_process_empty_dir(self):
        """空目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            miner = PatentMiner(input_dir=tmpdir)
            df = miner.batch_process()
            assert len(df) == 0

    def test_entity_map(self, temp_input_dir):
        """申请人名称映射"""
        miner = PatentMiner(
            input_dir=temp_input_dir,
            entity_map={"宁德时代新能源科技股份有限公司": "CATL"},
        )
        filepath = os.path.join(temp_input_dir, "test_patents.txt")
        df = miner.parse_txt(filepath)
        assert df.iloc[0]['applicants'] == 'CATL'

    def test_stopwords_loading(self, temp_input_dir):
        """停用词加载"""
        sw_path = os.path.join(temp_input_dir, "stopwords.txt")
        with open(sw_path, 'w', encoding='utf-8') as f:
            f.write("test\nword\n")
        miner = PatentMiner(input_dir=temp_input_dir, stopwords_path=sw_path)
        assert 'test' in miner.stopwords
        assert 'word' in miner.stopwords
