// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProviderProfile } from "../types";
import { createProviderProfile, discoverProviderModels } from "../api";
import { I18nProvider, useI18n } from "../i18n";
import { LLMAdvancedSettings } from "./LLMAdvancedSettings";

vi.mock("../api", () => ({
  activateProviderProfile: vi.fn(),
  createProviderProfile: vi.fn(),
  deleteProviderProfile: vi.fn(),
  discoverProviderModels: vi.fn(),
  probeProviderProfile: vi.fn(),
  updateProviderProfile: vi.fn(),
}));

const profile: ProviderProfile = {
  id: "provider-1", schema_version: 1, name: "学校网关", protocol: "openai_chat",
  notes: "仅供校内使用", website_url: "https://example.edu", base_url: "https://llm.example.edu/v1",
  model: "tool-model", selected: true, auth_mode: "bearer", auth_header_name: "Authorization",
  auth_prefix: "Bearer ", timeout_seconds: 60, max_retries: 2, max_output_tokens: 8192,
  temperature: null, reasoning_effort: "default", thinking_mode: "auto",
  model_discovery_path: "/models", extra_headers: [], extra_body: {}, credential_loaded: true,
  connected: false, needs_reconnect: false, created_at: "", updated_at: "",
  probe_status: "not_tested", probe_error_category: "", last_probe_at: "",
};

function LocaleSwitcher() {
  const { setLocale } = useI18n();
  return <button onClick={() => setLocale("en-US")}>English UI</button>;
}

describe("LLMAdvancedSettings", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => cleanup());

  it("fills a no-auth Ollama preset and keeps the form user editable", () => {
    render(<LLMAdvancedSettings open profiles={[]} isStreaming={false} onClose={vi.fn()} onRefresh={async () => []} onConnected={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ollama" }));
    expect(screen.getByDisplayValue("本地 Ollama")).toBeTruthy();
    expect(screen.getByDisplayValue("http://localhost:11434/v1")).toBeTruthy();
    expect(screen.getByDisplayValue("无鉴权")).toBeTruthy();
    expect(screen.queryByLabelText("API Key")).toBeNull();
  });

  it("never refills an in-memory API key into the browser", () => {
    render(<LLMAdvancedSettings open profiles={[profile]} isStreaming={false} onClose={vi.fn()} onRefresh={async () => [profile]} onConnected={vi.fn()} />);
    const key = screen.getByLabelText("接口密钥（API Key）") as HTMLInputElement;
    expect(key.value).toBe("");
    expect(key.placeholder).toContain("已在内存中加载");
  });

  it("rejects orchestrator-owned fields in Extra Body before saving", () => {
    render(<LLMAdvancedSettings open profiles={[profile]} isStreaming={false} onClose={vi.fn()} onRefresh={async () => [profile]} onConnected={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "请求参数与专家配置" }));
    const editor = screen.getByDisplayValue("{}") as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: '{"messages":[]}' } });
    expect(screen.getByText(/保留字段不能覆盖: messages/)).toBeTruthy();
  });

  it("can save an incomplete vLLM profile to discover models before choosing one", async () => {
    const saved = {
      ...profile, id: "provider-vllm", name: "本地 vLLM", model: "",
      base_url: "http://localhost:8001/v1", auth_mode: "none" as const,
      credential_loaded: true,
    };
    vi.mocked(createProviderProfile).mockResolvedValue(saved);
    vi.mocked(discoverProviderModels).mockResolvedValue({
      models: ["Qwen/Qwen3-32B"], latency_ms: 12, manual_entry_allowed: true,
    });
    render(<LLMAdvancedSettings open profiles={[]} isStreaming={false} onClose={vi.fn()} onRefresh={async () => [saved]} onConnected={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "vLLM" }));
    fireEvent.click(screen.getByRole("button", { name: /获取可用模型/ }));
    await waitFor(() => expect(discoverProviderModels).toHaveBeenCalledWith(
      "provider-vllm", { api_key: "", sensitive_headers: {} },
    ));
    expect(screen.getByRole("combobox", { name: "已发现模型" })).toBeTruthy();
    expect(screen.getByText("Qwen/Qwen3-32B")).toBeTruthy();
  });

  it("uses the active locale for new local and custom preset names", () => {
    render(
      <I18nProvider>
        <LocaleSwitcher />
        <LLMAdvancedSettings open profiles={[]} isStreaming={false} onClose={vi.fn()} onRefresh={async () => []} onConnected={vi.fn()} />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "English UI" }));
    fireEvent.click(screen.getByRole("button", { name: "Ollama" }));
    expect(screen.getByDisplayValue("Local Ollama")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.getByDisplayValue("Custom provider")).toBeTruthy();
  });

  it("does not rewrite a saved provider name when the locale changes", () => {
    render(
      <I18nProvider>
        <LocaleSwitcher />
        <LLMAdvancedSettings open profiles={[profile]} isStreaming={false} onClose={vi.fn()} onRefresh={async () => [profile]} onConnected={vi.fn()} />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "English UI" }));
    expect(screen.getByDisplayValue("学校网关")).toBeTruthy();
  });
});
