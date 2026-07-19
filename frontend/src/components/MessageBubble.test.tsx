// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MessageBubble } from "./MessageBubble";

describe("MessageBubble conversational recovery", () => {
  it("shows an inline summary retry action", () => {
    const retry = vi.fn();
    render(<MessageBubble message={{
      id: "a", role: "assistant", content: "总结未生成。",
      turnId: "turn-1", finalStatus: "partial", canResynthesize: true,
      error: "综合失败",
    }} onResynthesize={retry} />);
    expect(screen.getByText("综合失败")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "仅重试总结" }));
    expect(retry).toHaveBeenCalledWith("turn-1");
  });

  it("sends clarification defaults back to the pending turn", () => {
    const followup = vi.fn();
    render(<MessageBubble message={{
      id: "a", role: "assistant", content: "请提供关键词",
      followupQuestions: ["按默认条件继续"],
      clarification: { turnId: "turn-2", missingFields: ["query"], allowDefaults: true },
    }} onFollowup={followup} />);
    fireEvent.click(screen.getByRole("button", { name: "按默认条件继续" }));
    expect(followup).toHaveBeenCalledWith("按默认条件继续", "turn-2");
  });

  it("does not render legacy provider JSON syntax", () => {
    render(<MessageBubble message={{
      id: "legacy", role: "assistant",
      content: JSON.stringify({
        answer: "用户可读结论。",
        limitations: ["数据限制。"],
      }),
    }} />);
    expect(screen.getByText("核心结论")).toBeTruthy();
    expect(screen.getByText("用户可读结论。")).toBeTruthy();
    expect(screen.queryByText(/\{"answer"/)).toBeNull();
  });
});
