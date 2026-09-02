// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider, useI18n } from "../../i18n";
import { CapabilityCards } from "./CapabilityCards";

afterEach(() => {
  cleanup();
  document.documentElement.lang = "zh-CN";
});

function EnglishLocaleSwitch() {
  const { setLocale } = useI18n();
  return <button type="button" onClick={() => setLocale("en-US")}>switch to English</button>;
}

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

  it("uses the localized static prompt consistently for English UI", () => {
    const choose = vi.fn();
    render(<I18nProvider><><EnglishLocaleSwitch /><CapabilityCards capabilities={[{
        id: "technology_topics",
        name: "技术热点与主题",
        icon: "sparkles",
        description: "识别技术主题",
        tool_names: ["generate_wordcloud"],
        prompts: ["当前有哪些主要技术主题"],
        availability: "available",
        available_tool_count: 1,
        tool_count: 1,
        tools: [{ name: "generate_wordcloud", available: true }],
      }]} onPrompt={choose} /></></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: "switch to English" }));

    const prompt = "What are the main technology topics right now?";
    const button = screen.getByRole("button", { name: prompt });
    expect(button.getAttribute("title")).toBe(prompt);
    fireEvent.click(button);
    expect(choose).toHaveBeenCalledWith(prompt);
  });

  it("keeps an unknown capability prompt unchanged", () => {
    const choose = vi.fn();
    const prompt = "后端新增的预置问题";
    render(<I18nProvider><><EnglishLocaleSwitch /><CapabilityCards capabilities={[{
        id: "unknown_capability",
        name: "未知能力",
        icon: "sparkles",
        description: "未知描述",
        tool_names: [],
        prompts: [prompt],
        availability: "available",
        available_tool_count: 0,
        tool_count: 0,
        tools: [],
      }]} onPrompt={choose} /></></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: "switch to English" }));

    const button = screen.getByRole("button", { name: prompt });
    expect(button.getAttribute("title")).toBe(prompt);
    fireEvent.click(button);
    expect(choose).toHaveBeenCalledWith(prompt);
  });
});
