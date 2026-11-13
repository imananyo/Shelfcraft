import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./api";
import { formatBytes, providerLabel, timeAgo } from "./utils";

describe("utils", () => {
  it("formats bytes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
  it("formats relative time from naive UTC timestamps", () => {
    expect(timeAgo(new Date().toISOString().replace("Z", ""))).toBe("just now");
  });
  it("labels providers", () => {
    expect(providerLabel("local_diffusion")).toBe("Local diffusion");
    expect(providerLabel("unknown_x")).toBe("unknown_x");
  });
});

describe("api client", () => {
  afterEach(() => vi.restoreAllMocks());
  it("surfaces server error messages", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "name: required", code: "validation_error" }), { status: 422, headers: { "content-type": "application/json" } })));
    await expect(api("/x")).rejects.toMatchObject({ message: "name: required", status: 422, code: "validation_error" });
  });
  it("reports an unreachable backend clearly", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = (await api("/x").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toMatch(/backend/i);
  });
  it("never sends provider keys — only the optional local access token header", async () => {
    const spy = vi.fn(async (_url: string, _init?: RequestInit) => new Response("{}", { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", spy);
    await api("/settings");
    const headers = new Headers(spy.mock.calls[0][1]?.headers);
    expect([...headers.keys()].filter((k) => /key|authorization/i.test(k))).toEqual([]);
  });
});
