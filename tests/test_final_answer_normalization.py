import json

from agent.final_answer import (
    normalize_final_answer,
    parse_canonical_final_answer,
    user_facing_content,
)


def _deepseek_roadmap_shape() -> str:
    return json.dumps({
        "answer": "最近三年的技术路线从气体处理向直接空气捕集和碳封存演进。",
        "details": [
            {
                "year": 2020,
                "theme": "生活用水设备与工业气体处理",
                "representative_patents": ["CN210520788-U（气泡水制备装置）"],
            },
            {
                "year": 2021,
                "theme": "直接空气捕获与制氧集成",
                "representative_patents": ["WO2021188547-A1（直接空气捕获系统）"],
            },
            {
                "year": 2022,
                "theme": "温室气体液化与碳封存技术",
                "representative_patents": ["WO2022085952-A2（温室气体液化装置）"],
            },
        ],
        "trend_summary": "应用场景从低浓度二氧化碳处理向负排放技术扩展。",
        "methodology": "基于年度主题和代表性专利筛选。",
        "limitations": ["内部引证覆盖不足。", "不构成因果技术谱系。"],
        "follow_up_questions": [
            "是否深入分析直接空气捕获专利？",
            "是否比较主要申请人的布局变化？",
            "内部引证覆盖不足会如何影响可信度？",
        ],
    }, ensure_ascii=False)


def test_deepseek_alias_shape_becomes_user_facing_final_answer():
    raw = _deepseek_roadmap_shape()
    assert parse_canonical_final_answer(raw) is None

    normalized, mode = normalize_final_answer(raw, ["analyze_tech_roadmap"])

    assert mode == "local_repair"
    assert normalized is not None
    markdown = normalized["answer_markdown"]
    assert markdown.startswith("## 核心结论")
    assert "### 2020 年" in markdown
    assert "WO2021188547-A1" in markdown
    assert "## 趋势判断" in markdown
    assert "## 方法说明" in markdown
    assert "## 方法与数据限制" in markdown
    assert '"answer"' not in markdown
    assert normalized["evidence_refs"] == ["[analyze_tech_roadmap]"]
    assert len(normalized["followup_suggestions"]) == 3
    assert normalized["followup_suggestions"][2]["requires_new_tools"] is False


def test_canonical_final_answer_remains_unchanged():
    raw = json.dumps({
        "answer_markdown": "## 核心结论\n\n结果成立。",
        "evidence_refs": ["[demo:data]"],
        "followup_suggestions": [],
    }, ensure_ascii=False)
    normalized, mode = normalize_final_answer(raw)
    assert mode == "native"
    assert normalized == json.loads(raw)


def test_visible_content_never_returns_unrecognized_json_syntax():
    visible, normalized, mode = user_facing_content("{}")
    assert normalized is None
    assert mode == "fallback"
    assert visible.startswith("## 分析结果")
    assert visible.strip() != "{}"
