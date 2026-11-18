import { describe, expect, it } from "vitest";
import { defaultStep, estimateMinutes, formatMinutes, runSummary, stepLabel } from "./playbooks";

describe("playbook helpers", () => {
  it("switching kind gives a clean step", () => {
    expect(defaultStep("creative")).toEqual({ kind: "creative", creative_type: "lifestyle" });
    expect(defaultStep("research")).toEqual({ kind: "research" });
    expect(defaultStep("video")).not.toHaveProperty("creative_type");
  });
  it("labels steps readably", () => {
    expect(stepLabel({ kind: "creative", creative_type: "white_bg_main" })).toBe("white bg main");
    expect(stepLabel({ kind: "creative", creative_type: "hero" }, { creative_types: { hero: "Premium hero image" } })).toBe("Premium hero image");
    expect(stepLabel({ kind: "listing_copy", marketplace: "walmart", language: "de" })).toBe("Listing copy · walmart · DE");
    expect(stepLabel({ kind: "video", aspect: "9:16", voiceover: true })).toBe("Video 9:16 + voiceover");
  });
  it("estimates and formats run time", () => {
    expect(estimateMinutes([{ kind: "creative" }, { kind: "research" }], 2)).toBe(8);
    expect(formatMinutes(0.5)).toBe("under a minute");
    expect(formatMinutes(14.6)).toBe("~15 min");
    expect(formatMinutes(125)).toBe("~2 h 5 min");
  });
  it("summarises runs", () => {
    expect(runSummary({ id: "a", total: 3, created_at: "", counts: { succeeded: 2, running: 1 } }).state).toBe("running");
    expect(runSummary({ id: "a", total: 3, created_at: "", counts: { succeeded: 2, failed: 1 } }).state).toBe("failed");
    expect(runSummary({ id: "a", total: 3, created_at: "", counts: { succeeded: 3 } })).toMatchObject({ done: 3, state: "done" });
  });
});
