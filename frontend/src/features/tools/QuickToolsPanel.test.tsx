// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider, useI18n } from "../../i18n";
import { QuickToolsPanel } from "./QuickToolsPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.documentElement.lang = "zh-CN";
});

function EnglishLocaleSwitch() {
  const { setLocale } = useI18n();
  return <button type="button" onClick={() => setLocale("en-US")}>switch to English</button>;
}

const searchTool = {
  name: "search_patents",
  description: "检索",
  parameters: {
    query: { type: "string" as const, required: true },
    retrieval_mode: {
      type: "string" as const,
      enum: ["lexical", "multilingual_hybrid_beta"],
    },
  },
};

describe("QuickToolsPanel MiniLM visibility", () => {
  it("shows runtime/cache status without requiring the tool row to be discovered", () => {
    render(<QuickToolsPanel
      tools={[searchTool]}
      isStreaming={false}
      loadingTool={null}
      searchStatus={{
        model_id: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        dependency_installed: true,
        model_cached: true,
        model_cache_directory: "/cache/model",
        index_cache_directory: "/cache/index",
        index_count: 2,
        download_size_mb: 471,
        modes: ["lexical", "multilingual_hybrid_beta"],
      }}
      onRun={vi.fn()}
      className="flex"
    />);

    expect(screen.getByText("MiniLM 多语言语义检索（测试版）")).toBeTruthy();
    expect(screen.getByText("模型已缓存 · 2 个数据集索引")).toBeTruthy();
    expect(screen.getByText("多语言向量检索（测试版）")).toBeTruthy();
  });

  it("passes the explicit beta mode only when selected", () => {
    const run = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<QuickToolsPanel
      tools={[searchTool]}
      isStreaming={false}
      loadingTool={null}
      onRun={run}
      className="flex"
    />);

    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByLabelText(/检索词/), { target: { value: "碳捕集膜" } });
    fireEvent.click(screen.getByRole("button", { name: "执行" }));
    expect(run).toHaveBeenCalledWith("search_patents", {
      query: "碳捕集膜",
      retrieval_mode: "multilingual_hybrid_beta",
    });
  });

  it("uses the localized tool label instead of backend description for available titles", () => {
    render(<I18nProvider><><EnglishLocaleSwitch /><QuickToolsPanel
        tools={[{ ...searchTool, description: "后端静态中文描述" }]}
        isStreaming={false}
        loadingTool={null}
        onRun={vi.fn()}
        className="flex"
      /></></I18nProvider>);
    fireEvent.click(screen.getByRole("button", { name: "switch to English" }));

    const button = screen.getByRole("button", { name: /Related patent search/ });
    expect(button.getAttribute("title")).toBe("Related patent search");
    expect(button.getAttribute("title")).not.toContain("后端静态中文描述");
  });
});
