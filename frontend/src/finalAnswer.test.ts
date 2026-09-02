import { describe, expect, it } from "vitest";

import { normalizeAssistantContent } from "./finalAnswer";


describe("user-facing final answer normalization", () => {
  it("renders DeepSeek alias JSON as a report with separate followups", () => {
    const raw = JSON.stringify({
      answer: "最近三年技术路线逐步升级。",
      details: [
        { year: 2020, theme: "工业气体处理", representative_patents: ["CN1"] },
        { year: 2021, theme: "直接空气捕获", representative_patents: ["WO2"] },
      ],
      trend_summary: "路线向负排放技术扩展。",
      methodology: "基于年度主题统计。",
      limitations: ["引证覆盖不足。"],
      follow_up_questions: ["是否查看代表专利？", "限制会如何影响可信度？"],
    });
    const result = normalizeAssistantContent(raw);
    expect(result.content).toContain("## 核心结论");
    expect(result.content).toContain("### 2020 年");
    expect(result.content).toContain("## 方法与数据限制");
    expect(result.content).not.toContain('"answer"');
    expect(result.followupQuestions).toEqual(["是否查看代表专利？", "限制会如何影响可信度？"]);
    expect(result.followupSuggestions[1].requires_new_tools).toBe(false);
  });

  it("never exposes an empty JSON object", () => {
    const result = normalizeAssistantContent("{}");
    expect(result.normalizationMode).toBe("fallback");
    expect(result.content).toContain("无法识别的结构化结果");
    expect(result.content).not.toBe("{}");
  });

  it("localizes client-generated report wrappers without translating model values", () => {
    const result = normalizeAssistantContent(JSON.stringify({
      answer: "模型原文结论",
      details: [{ year: 2020, theme: "用户提供的技术主题", representative_patents: ["CN-USER-1"] }],
    }), "en-US");
    expect(result.content).toContain("## Key conclusion");
    expect(result.content).toContain("### 2020 Year");
    expect(result.content).toContain("模型原文结论");
    expect(result.content).toContain("用户提供的技术主题");
    expect(result.content).toContain("CN-USER-1");
    expect(result.content).not.toContain("## 核心结论");
  });
});
