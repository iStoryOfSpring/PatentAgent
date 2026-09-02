// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n";
import { DatasetsPage } from "../datasets/DatasetsPage";
import { AppShell } from "./AppShell";

function createStorage(initialLocale = "zh-CN") {
  const values = new Map<string, string>([["patentagent.locale", initialLocale]]);
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => values.set(key, value)),
    removeItem: vi.fn((key: string) => values.delete(key)),
    clear: vi.fn(() => values.clear()),
    key: vi.fn((index: number) => Array.from(values.keys())[index] ?? null),
    get length() { return values.size; },
  } as unknown as Storage;
}

describe("global language switch", () => {
  let storage: Storage;

  beforeEach(() => {
    storage = createStorage();
    Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    document.documentElement.lang = "zh-CN";
  });

  it("updates the shell and a key page without changing data values", () => {
    const navigate = vi.fn();
    render(
      <I18nProvider>
        <AppShell route="datasets" onNavigate={navigate} backendOnline={true}
          datasetLabel="演示数据" llmLabel="DeepSeek" taskRunning={true}>
          <DatasetsPage datasets={[{
            id: "dataset-1",
            name: "用户数据集",
            source_root: "./data",
            status: "ready",
            version_count: 1,
            latest_version: {
              dataset_id: "dataset-1",
              id: "version-1",
              version_id: "version-1",
              content_hash: "hash-1",
              schema_version: 1,
              record_count: 2,
              adapter: "wos_dii",
              sources: [],
              field_coverage: {},
            },
          }]} activeSessionId="session-1" activeVersionId="version-1"
            onChanged={vi.fn()} onError={vi.fn()} />
        </AppShell>
      </I18nProvider>,
    );

    expect((screen.getByRole("combobox", { name: "语言" }) as HTMLSelectElement).value).toBe("zh-CN");
    expect(screen.getByRole("heading", { name: "数据集工作区" })).toBeTruthy();
    expect(screen.getByText("用户数据集")).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox", { name: "语言" }), { target: { value: "en-US" } });

    expect((screen.getByRole("combobox", { name: "Language" }) as HTMLSelectElement).value).toBe("en-US");
    expect(screen.getByRole("heading", { name: "Dataset workspace" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Analysis" })).toBeTruthy();
    expect(screen.getByText("用户数据集")).toBeTruthy();
    expect(document.documentElement.lang).toBe("en-US");
    expect(storage.setItem).toHaveBeenCalledWith("patentagent.locale", "en-US");

    const select = screen.getByRole("combobox", { name: "Language" });
    expect(select.className).toContain("shrink-0");
    expect(select.className).toContain("max-w");
  });

  it("initializes a new dataset name in English once and preserves edits after switching", () => {
    storage = createStorage("en-US");
    Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
    render(
      <I18nProvider>
        <AppShell route="datasets" onNavigate={vi.fn()} backendOnline={true}
          datasetLabel="" llmLabel="" taskRunning={false}>
          <DatasetsPage datasets={[]} activeSessionId="session-1" activeVersionId=""
            onChanged={vi.fn()} onError={vi.fn()} />
        </AppShell>
      </I18nProvider>,
    );

    const name = screen.getByDisplayValue("Mentor demo dataset") as HTMLInputElement;
    fireEvent.change(name, { target: { value: "My dataset" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "zh-CN" } });

    expect(screen.getByDisplayValue("My dataset")).toBeTruthy();
  });
});
