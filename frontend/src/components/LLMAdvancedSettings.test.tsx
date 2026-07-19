// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProviderProfile } from "../types";
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
};

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
    const key = screen.getByLabelText("API Key") as HTMLInputElement;
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
});
