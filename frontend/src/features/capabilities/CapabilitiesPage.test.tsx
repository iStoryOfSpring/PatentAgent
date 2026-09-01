// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CapabilitiesPage } from "./CapabilitiesPage";

afterEach(cleanup);

describe("CapabilitiesPage", () => {
  it("keeps quick tools in a top-aligned, independently scrollable desktop column", () => {
    render(
      <CapabilitiesPage
        capabilities={[{
          id: "patent_search",
          name: "专利检索",
          icon: "search",
          description: "从当前语料中筛选相关专利。",
          tool_names: ["search_patents"],
          prompts: ["检索相关专利"],
          availability: "available",
          available_tool_count: 1,
          tool_count: 1,
          tools: [{ name: "search_patents", available: true }],
        }]}
        tools={[{
          name: "search_patents",
          description: "检索",
          parameters: {},
        }]}
        loadingTool={null}
        isStreaming={false}
        onPrompt={vi.fn()}
        onRun={vi.fn()}
      />,
    );

    const panel = screen.getByRole("complementary");
    const panelWrapper = panel.parentElement;
    expect(panelWrapper?.className).toContain("lg:sticky");
    expect(panelWrapper?.className).toContain("lg:top-0");
    expect(panel.className).toContain("lg:overflow-y-auto");
  });
});
