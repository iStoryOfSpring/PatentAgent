// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapabilityCards } from "./CapabilityCards";

afterEach(cleanup);

describe("CapabilityCards", () => {
  it("shows dynamic availability and fills a prompt without running a tool", () => {
    const choose = vi.fn();
    render(<CapabilityCards capabilities={[{
      id: "technology_topics",
      name: "技术热点与主题",
      icon: "sparkles",
      description: "识别技术主题",
      tool_names: ["generate_wordcloud", "analyze_clustering"],
      prompts: ["当前有哪些主要技术主题"],
      availability: "partial",
      available_tool_count: 1,
      tool_count: 2,
      tools: [
        { name: "generate_wordcloud", available: true },
        { name: "analyze_clustering", available: false, reason: "至少需要 100 条文本" },
      ],
    }]} onPrompt={choose} />);

    expect(screen.getByText("1/2 可用")).toBeTruthy();
    expect(screen.getByText("部分工具因字段门槛降级")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "当前有哪些主要技术主题" }));
    expect(choose).toHaveBeenCalledWith("当前有哪些主要技术主题");
  });
});
