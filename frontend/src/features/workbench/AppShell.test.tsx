// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

afterEach(cleanup);

it("navigates between the five workbench areas and exposes status", () => {
  const navigate = vi.fn();
  render(<AppShell route="chat" onNavigate={navigate} backendOnline={true}
    datasetLabel="演示数据" llmLabel="DeepSeek" taskRunning={false}
    context={<div>会话列表</div>}><div>对话区</div></AppShell>);

  expect(screen.getByText("演示数据")).toBeTruthy();
  expect(screen.getByText("DeepSeek")).toBeTruthy();
  expect(screen.getByText("会话列表")).toBeTruthy();
  expect(screen.getByRole("link", { name: /GitHub 仓库/ }).getAttribute("href"))
    .toBe("https://github.com/iStoryOfSpring/PatentAgent");
  fireEvent.click(screen.getByRole("button", { name: "数据集" }));
  expect(navigate).toHaveBeenCalledWith("datasets");
  fireEvent.click(screen.getByRole("button", { name: "报告" }));
  expect(navigate).toHaveBeenCalledWith("reports");
});
