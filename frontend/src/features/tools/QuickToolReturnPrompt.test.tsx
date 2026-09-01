// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QuickToolReturnPrompt } from "./QuickToolReturnPrompt";

afterEach(() => cleanup());

describe("QuickToolReturnPrompt", () => {
  it("offers a return-to-chat action and a persisted preference callback", () => {
    const onDontRemindChange = vi.fn();
    const onReturnToChat = vi.fn();
    const onStay = vi.fn();
    render(<QuickToolReturnPrompt
      open
      dontRemind={false}
      onDontRemindChange={onDontRemindChange}
      onStay={onStay}
      onReturnToChat={onReturnToChat}
    />);

    expect(screen.getByRole("heading", { name: "工具执行完成" })).toBeTruthy();
    fireEvent.click(screen.getByLabelText("以后不再提示"));
    fireEvent.click(screen.getByRole("button", { name: "回到聊天页面" }));
    expect(onDontRemindChange).toHaveBeenCalledWith(true);
    expect(onReturnToChat).toHaveBeenCalledTimes(1);
    expect(onStay).not.toHaveBeenCalled();
  });
});
