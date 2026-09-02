// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { streamChat } from "./api";
import type { SSEEvent } from "./types";

function responseWith(body: string): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(body));
      controller.close();
    },
  });
  return new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

afterEach(() => vi.restoreAllMocks());

describe("streamChat protocol guard", () => {
  it("accepts a stream only after one done event", async () => {
    const done = {
      type: "done", session_id: "s", turn_id: "t", final_status: "completed",
      answer_present: true, result_coverage: [], coverage_complete: true,
      new_execution_ids: [], reused_execution_ids: [],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseWith(
      `data: ${JSON.stringify({ type: "text", content: "总结" })}\n\n` +
      `data: ${JSON.stringify(done)}\n\n`,
    )));
    const events: SSEEvent[] = [];
    await new Promise<void>((resolve, reject) => {
      streamChat("q", "s", "detailed", event => events.push(event), resolve, reject);
    });
    expect(events.map(event => event.type)).toEqual(["text", "done"]);
  });

  it("reports malformed SSE instead of silently skipping it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseWith("data: {not-json}\n\n")));
    const error = await new Promise<Error>((resolve) => {
      streamChat("q", "s", "detailed", () => undefined, () => {
        throw new Error("must not complete");
      }, resolve);
    });
    expect(error.message).toBe("client.sse.invalidEvent");
  });

  it("reports EOF before done", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(responseWith(
      `data: ${JSON.stringify({ type: "text", content: "未完成" })}\n\n`,
    )));
    const error = await new Promise<Error>((resolve) => {
      streamChat("q", "s", "detailed", () => undefined, () => {
        throw new Error("must not complete");
      }, resolve);
    });
    expect(error.message).toBe("client.sse.incomplete");
  });
});
